"""FastAPI server: JSON API + the web dashboard.

Run from the project root:
    uvicorn backend.app.main:app --reload
Then open http://127.0.0.1:8000
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import backtest
from .config import ROOT, settings
from .data.intermarket import get_intermarket
from .data.providers import DataError, get_candles
from .engine import EngineConfig, decide, votes_at
from .features import build_features
from .news.calendar import get_events, high_impact
from .news.sentiment import get_news
from .strategies import BUY, STRATEGIES, Ctx

log = logging.getLogger("xauusd")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
FRONTEND = ROOT / "frontend"
CFG = EngineConfig()


# Latest news / calendar / intermarket results. Filled by the background thread so that
# API requests never wait on slow external websites.
_context: dict = {
    "news": {"bias": 0.0, "headlines": [], "model": "loading"},
    "events": [],
    "intermarket": {"bias": 0.0, "ok": False},
}


def _refresh_loop() -> None:
    """Keeps news, calendar and dollar/yield data fresh in the background."""
    while True:
        for key, fn in (("events", get_events), ("intermarket", get_intermarket), ("news", get_news)):
            try:
                _context[key] = fn()
            except Exception as e:  # never let the background thread die
                log.warning("background refresh %s failed: %s", key, e)
        time.sleep(300)


@asynccontextmanager
async def lifespan(_: FastAPI):
    threading.Thread(target=_refresh_loop, daemon=True).start()
    yield


app = FastAPI(title="AI Trading Assist - XAUUSD", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

# ---------------------------------------------------------------- cached computation

_lock = threading.Lock()
_memo: dict = {"key": None}


def _market():
    """Candles + features + context, recomputed only when a new candle arrives."""
    try:
        df = get_candles()
    except DataError as e:
        raise HTTPException(503, str(e)) from e
    except Exception as e:  # network / provider errors
        raise HTTPException(503, f"Data provider '{settings.data_provider}' failed: {e}") from e
    key = (settings.data_provider, df.index[-1], len(df))
    with _lock:
        if _memo["key"] != key:
            f = build_features(df)
            _memo.update(key=key, df=df, f=f, x=Ctx(f), backtest=None)
        return _memo


def trade_status(x: Ctx, i: int, sig: dict) -> tuple[bool, str, int]:
    """What happened to a signal created at bar i, up to the latest bar.
    Returns (still_open, description, bar where it ended or the last bar). Same rules as the backtest."""
    d = BUY if sig["direction"] == "BUY" else -1
    H, L = x["high"], x["low"]
    filled, tp_hits, stop, fill_bar = False, 0, sig["sl"], None
    tps = [sig["tp1"], sig["tp2"], sig["tp3"]]
    for k in range(i + 1, x.n):
        if not filled:
            if k - i > CFG.zone_valid_bars:
                return False, "expired (entry zone not reached)", k
            if (L[k] <= sig["entry"]) if d == BUY else (H[k] >= sig["entry"]):
                filled, fill_bar = True, k
            elif (H[k] >= tps[0]) if d == BUY else (L[k] <= tps[0]):
                return False, "missed (TP1 reached before entry)", k
            else:
                continue
        if k - fill_bar >= backtest.MAX_HOLD:
            return False, "closed after 24 hours", k
        if (L[k] <= stop) if d == BUY else (H[k] >= stop):
            text = "stopped out" if tp_hits == 0 else ("closed at break-even" if tp_hits == 1 else f"closed after TP{tp_hits}")
            return False, text, k
        while tp_hits < 3 and ((H[k] >= tps[tp_hits]) if d == BUY else (L[k] <= tps[tp_hits])):
            tp_hits += 1
            stop = sig["entry"] if tp_hits == 1 else tps[0]
        if tp_hits == 3:
            return False, "TP3 hit - trade complete", k
    if not filled:
        return True, "waiting for price to reach the entry zone", x.n - 1
    if tp_hits == 0:
        return True, "in trade", x.n - 1
    return True, f"TP{tp_hits} hit - stop moved to {'break-even' if tp_hits == 1 else 'TP1'}", x.n - 1


# ---------------------------------------------------------------- routes


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/status")
def status():
    return {
        "symbol": "XAUUSD",
        "provider": settings.data_provider,
        "news_model": "claude" if settings.anthropic_api_key else "keywords",
        "claude_model": settings.claude_model if settings.anthropic_api_key else None,
        "account_balance": settings.account_balance,
        "risk_percent": settings.risk_percent,
        "strategies": [{"name": s.name, "label": s.label, "description": s.description} for s in STRATEGIES],
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/candles")
def candles(tf: str = Query("15m", pattern="^(15m|1h|4h)$"), limit: int = Query(800, ge=50, le=5000)):
    m = _market()
    df = m["df"]
    if tf != "15m":
        rule = {"1h": "1h", "4h": "4h"}[tf]
        df = df.resample(rule, label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    df = df.tail(limit)
    close = df["close"]
    ema = {n: close.ewm(span=n, adjust=False).mean() for n in (20, 50, 200)}
    t = [int(ts.timestamp()) for ts in df.index]
    return {
        "tf": tf,
        "candles": [{"time": ti, "open": o, "high": h, "low": l, "close": c}
                    for ti, o, h, l, c in zip(t, df["open"], df["high"], df["low"], df["close"])],
        "ema": {str(n): [{"time": ti, "value": float(v)} for ti, v in zip(t, s)] for n, s in ema.items()},
    }


@app.get("/api/analysis")
def analysis():
    m = _market()
    x: Ctx = m["x"]
    last = x.n - 1
    news, inter, events = _context["news"], _context["intermarket"], _context["events"]
    hi_events = high_impact(events)

    # Replay the last day the same way the backtest does (one trade at a time), so a signal keeps
    # its original zone / SL / TP instead of being recalculated on every new candle.
    look = backtest.MAX_HOLD + CFG.zone_valid_bars
    first = max(backtest.WARMUP, last - look)
    history = {i: v for i in range(max(0, first - CFG.vote_ttl_bars), last + 1) if (v := votes_at(x, i))}
    now_view = decide(x, last, history, CFG, news["bias"], inter["bias"], hi_events)
    active = None
    i = first
    while i <= last:
        a = now_view if i == last else decide(x, i, history, CFG, news["bias"], inter["bias"], hi_events)
        if not a["signal"]:
            i += 1
            continue
        sig = dict(a["signal"])
        still_open, text, end = trade_status(x, i, sig)
        sig.update(created=x.index[i].isoformat(), status=text, open=still_open)
        active = sig  # the newest signal wins; a finished one is still shown until a new one appears
        if still_open:
            break
        i = end + 1

    levels = {k: round(x.v(c, last), 2) for k, c in (
        ("prev_day_high", "pd_high"), ("prev_day_low", "pd_low"), ("asia_high", "asia_hi"),
        ("asia_low", "asia_lo"), ("swing_high", "sh1"), ("swing_low", "sl1"), ("vwap", "vwap"))
        if not pd.isna(x.v(c, last))}
    now = pd.Timestamp.now(tz="UTC")
    upcoming = [e for e in events if pd.Timestamp(e["time"]) >= now - pd.Timedelta(hours=1)][:10]
    return {
        **now_view,
        "active_signal": active,
        "levels": levels,
        "news_bias": news["bias"],
        "intermarket": inter,
        "upcoming_events": upcoming,
        "data_age_minutes": round((now - (x.index[last] + pd.Timedelta(minutes=15))).total_seconds() / 60, 1),
    }


@app.get("/api/news")
def news():
    return _context["news"]


@app.get("/api/calendar")
def calendar():
    return {"events": _context["events"]}


@app.get("/api/backtest")
def run_backtest():
    m = _market()
    with _lock:
        if m.get("backtest") is None:
            m["backtest"] = backtest.run(m["df"], CFG)
        return m["backtest"]
