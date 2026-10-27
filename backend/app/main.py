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

from . import backtest, ml
from .ai import llm
from .ai.analyst import analyst, build_snapshot
from .config import ROOT, settings
from .data.intermarket import get_intermarket
from .data.providers import DataError, get_candles
from .engine import EngineConfig, decide, grade_for, plan_from_levels, time_block, votes_at
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


def _live_cfg():
    """With a trained ML model, the engine uses the model's looser candidate rules and lets the model decide."""
    meta = ml.load()
    if meta is None:
        return CFG, None
    return EngineConfig(min_agree=meta.min_agree, min_score=meta.min_score), meta


_PUBLIC = ("status", "action", "confidence", "agrees_with_engine", "summary", "reasons", "risks",
           "summary_id", "reasons_id", "risks_id",
           "problems", "levels_ok", "provider", "model", "decided_at", "error", "zone_low", "zone_high", "sl", "tp1", "tp2", "tp3")


def _public(v: dict | None) -> dict | None:
    return None if v is None else {k: v[k] for k in _PUBLIC if k in v}


def _apply_ai(x: Ctx, i: int, sig: dict, v: dict | None, cfg: EngineConfig) -> dict:
    """Combine an engine signal with Claude's verdict: confirm, adjust the levels, or reject."""
    sig["ai"] = _public(v) or {"status": "not reviewed"}
    if not v or v.get("status") != "ok":
        sig["ai_status"] = {"pending": "analysing", "queued": "analysing", "error": "error"}.get(
            (v or {}).get("status"), "not reviewed")
        return sig
    if v["action"] != sig["direction"]:
        sig["ai_status"] = "rejected"
        return sig
    sig["ai_status"] = "confirmed"
    if v.get("levels_ok"):
        d = BUY if v["action"] == "BUY" else -1
        new = plan_from_levels(x, i, d, v["zone_low"], v["zone_high"], v["sl"], [v["tp1"], v["tp2"], v["tp3"]], cfg)
        changed = any(abs(new[k] - sig[k]) > 0.05 for k in ("zone_low", "zone_high", "sl", "tp1", "tp2", "tp3"))
        if changed:
            sig["engine_levels"] = {k: sig[k] for k in ("zone_low", "zone_high", "entry", "sl", "tp1", "tp2", "tp3")}
            sig.update(new)
            sig["ai_status"] = "adjusted"
    return sig


def _ai_own_signal(x: Ctx, i: int, v: dict, cfg: EngineConfig) -> dict:
    d = BUY if v["action"] == "BUY" else -1
    sig = plan_from_levels(x, i, d, v["zone_low"], v["zone_high"], v["sl"], [v["tp1"], v["tp2"], v["tp3"]], cfg)
    sig.update(score=float(v["confidence"]), grade=grade_for(v["confidence"]), strategies=[],
               reasons=v.get("reasons", []), against=v.get("risks", []), source="ai",
               ai=_public(v), ai_status="ai signal")
    return sig


# ---------------------------------------------------------------- routes


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/status")
def status():
    return {
        "symbol": "XAUUSD",
        "provider": settings.data_provider,
        "ai_provider": llm.provider(),
        "ai_model": llm.model_name(),
        "news_model": llm.provider() or "keywords",
        "ai_signal_mode": settings.ai_signal_mode if analyst.enabled else "off",
        "ml_model": (m.report if (m := ml.load()) else None),
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

    cfg, meta = _live_cfg()
    ai_on = analyst.enabled
    full_ai = ai_on and settings.ai_signal_mode == "full"

    def ask(key: str, i: int, view: dict, candidate: dict | None) -> dict:
        snap = build_snapshot(x, i, view, candidate, news, events, inter)
        return analyst.submit(key, snap, x.v("close", i), x.v("atr", i))

    # Replay the last day the same way the backtest does (one trade at a time), so a signal keeps
    # its original zone / SL / TP instead of being recalculated on every new candle.
    look = backtest.MAX_HOLD + cfg.zone_valid_bars
    first = max(backtest.WARMUP, last - look)
    history = {i: v for i in range(max(0, first - cfg.vote_ttl_bars), last + 1) if (v := votes_at(x, i))}
    now_view = decide(x, last, history, cfg, news["bias"], inter["bias"], hi_events, meta)
    active = None
    i = first
    while i <= last:
        a = now_view if i == last else decide(x, i, history, cfg, news["bias"], inter["bias"], hi_events, meta)
        t_key = x.index[i].isoformat()
        sig = None
        if a["signal"]:
            sig = dict(a["signal"])
            if ai_on:
                v = analyst.get("sig:" + t_key)
                if v is None and trade_status(x, i, sig)[0]:  # only ask about signals that are still live
                    v = ask("sig:" + t_key, i, a, sig)
                sig = _apply_ai(x, i, sig, v, cfg)
        elif full_ai:
            v = analyst.get("scan:" + t_key)
            if v and v.get("status") == "ok" and v["action"] in ("BUY", "SELL") and v.get("levels_ok"):
                sig = _ai_own_signal(x, i, v, cfg)
        if sig is None:
            i += 1
            continue
        sig["created"] = t_key
        if sig.get("ai_status") == "rejected":
            sig.update(status="rejected by the AI analyst", open=False)
            active = sig
            i += cfg.vote_ttl_bars  # the same setup would come back on the next candles: skip it
            continue
        still_open, text, end = trade_status(x, i, sig)
        sig.update(status=text, open=still_open)
        active = sig  # the newest signal wins; a finished one is still shown until a new one appears
        if still_open:
            break
        i = end + 1

    # full mode: no live trade -> ask Claude to look for one on the newest candle
    ai_scan = None
    if full_ai and not (active and active["open"]):
        key = "scan:" + x.index[last].isoformat()
        ai_scan = analyst.get(key)
        if ai_scan is None and now_view["votes"] and not time_block(x.index[last] + pd.Timedelta(minutes=15)):
            ai_scan = ask(key, last, now_view, None)
    now_view.pop("ml_features", None)

    levels = {k: round(x.v(c, last), 2) for k, c in (
        ("prev_day_high", "pd_high"), ("prev_day_low", "pd_low"), ("asia_high", "asia_hi"),
        ("asia_low", "asia_lo"), ("swing_high", "sh1"), ("swing_low", "sl1"), ("vwap", "vwap"))
        if not pd.isna(x.v(c, last))}
    now = pd.Timestamp.now(tz="UTC")
    upcoming = [e for e in events if pd.Timestamp(e["time"]) >= now - pd.Timedelta(hours=1)][:10]
    return {
        **now_view,
        "active_signal": active,
        "ai_scan": _public(ai_scan),
        "ai_mode": settings.ai_signal_mode if ai_on else "off",
        "ml_model": meta.report if meta else None,
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
