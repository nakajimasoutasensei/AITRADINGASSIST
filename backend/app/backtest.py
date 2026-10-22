"""Bar-by-bar backtest of the signal engine.

Rules (same as live):
  * a signal places a limit order at the middle of the entry zone, valid for `zone_valid_bars`
  * the order is cancelled if price reaches TP1 or SL before filling
  * TP1 hit -> close 50%, stop moves to break-even; TP2 -> close 30%; TP3 -> close the rest
  * if SL and a TP are touched in the same candle, we assume SL came first (pessimistic)
  * spread is paid on every fill; trades still open after 24h are closed at market
Results are in R (1R = the amount risked).

Run:  python -m backend.app.backtest [--provider synthetic|yfinance|twelvedata|mt5] [--csv file.csv]
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass

import pandas as pd

from .engine import EngineConfig, decide, votes_at
from .features import build_features
from .strategies import BUY, Ctx

WARMUP = 300
MAX_HOLD = 96


@dataclass
class Trade:
    signal_time: str
    direction: str
    grade: str
    score: float
    strategies: list
    entry: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    fill_time: str | None = None
    exit_time: str | None = None
    result_r: float = 0.0
    tp1_hit: bool = False
    outcome: str = "expired"  # expired | missed | stopped | breakeven | tp1 | tp2 | tp3 | timeout


def compute_votes(x: Ctx, start: int = WARMUP) -> dict:
    return {i: v for i in range(start, x.n) if (v := votes_at(x, i))}


def simulate(x: Ctx, i: int, sig: dict, spread: float) -> tuple[Trade, int]:
    """Returns the trade and the bar index where it ended."""
    d = BUY if sig["direction"] == "BUY" else -1
    t = Trade(x.index[i].isoformat(), sig["direction"], sig["grade"], sig["score"], sig["strategies"],
              sig["entry"], sig["sl"], sig["tp1"], sig["tp2"], sig["tp3"])
    H, L, C = x["high"], x["low"], x["close"]
    entry, sl = sig["entry"], sig["sl"]
    risk = abs(entry - sl)
    tps = [sig["tp1"], sig["tp2"], sig["tp3"]]
    portions = [0.5, 0.3, 0.2]

    # 1) wait for fill
    fill = None
    last = min(i + 1 + 8, x.n)
    for k in range(i + 1, last):
        hit_entry = L[k] <= entry if d == BUY else H[k] >= entry
        if hit_entry:
            fill = k
            break
        if (H[k] >= tps[0]) if d == BUY else (L[k] <= tps[0]):
            t.outcome = "missed"
            return t, k
        if (L[k] <= sl) if d == BUY else (H[k] >= sl):
            t.outcome = "expired"
            return t, k
    if fill is None:
        return t, last - 1
    t.fill_time = x.index[fill].isoformat()

    # 2) manage the position
    eff_entry = entry + d * spread  # pay the spread
    open_part, realized, stop, n_tp = 1.0, 0.0, sl, 0

    def pnl(price: float) -> float:
        return d * (price - eff_entry) / risk

    for k in range(fill, min(fill + MAX_HOLD, x.n)):
        stop_hit = (L[k] <= stop) if d == BUY else (H[k] >= stop)
        if stop_hit:
            realized += open_part * pnl(stop)
            open_part = 0
            t.outcome = "stopped" if n_tp == 0 else ("breakeven" if n_tp == 1 else f"tp{n_tp}")
            t.exit_time = x.index[k].isoformat()
            break
        while n_tp < 3 and ((H[k] >= tps[n_tp]) if d == BUY else (L[k] <= tps[n_tp])):
            realized += portions[n_tp] * pnl(tps[n_tp])
            open_part -= portions[n_tp]
            n_tp += 1
            if n_tp == 1:
                t.tp1_hit = True
                stop = entry  # break-even
            elif n_tp == 2:
                stop = tps[0]  # lock in TP1
        if n_tp == 3:
            t.outcome = "tp3"
            t.exit_time = x.index[k].isoformat()
            open_part = 0
            break
    if open_part > 0:
        k = min(fill + MAX_HOLD, x.n) - 1
        realized += open_part * pnl(C[k])
        t.outcome = "timeout" if n_tp == 0 else f"tp{n_tp}"
        t.exit_time = x.index[k].isoformat()
    t.result_r = round(float(realized), 3)
    return t, k


def run(df: pd.DataFrame, cfg: EngineConfig | None = None, meta=None) -> dict:
    """meta: optional trained ML model. Note: testing it on the data it was trained on is too optimistic;
    the honest numbers are in the model's own report (test period it never saw)."""
    cfg = cfg or EngineConfig()
    f = build_features(df)
    x = Ctx(f)
    history = compute_votes(x)
    trades: list[Trade] = []
    i = WARMUP
    while i < x.n - 1:
        if i not in history:
            i += 1
            continue
        a = decide(x, i, history, cfg, meta=meta)
        sig = a["signal"]
        if sig is None:
            i += 1
            continue
        t, end = simulate(x, i, sig, cfg.spread)
        trades.append(t)
        i = max(end, i) + 1  # one position at a time
    return {"trades": [t.__dict__ for t in trades], "stats": stats(trades), "bars": x.n,
            "start": str(df.index[0]), "end": str(df.index[-1])}


def _summary(ts: list[Trade]) -> dict:
    filled = [t for t in ts if t.fill_time]
    if not filled:
        return {"signals": len(ts), "trades": 0}
    rs = [float(t.result_r) for t in filled]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]
    equity, peak, dd = 0.0, 0.0, 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        dd = min(dd, equity - peak)
    return {
        "signals": len(ts),
        "trades": len(filled),
        "win_rate_tp1": round(100 * sum(t.tp1_hit for t in filled) / len(filled), 1),
        "profitable_pct": round(100 * len(wins) / len(filled), 1),
        "full_losses_pct": round(100 * sum(t.outcome == "stopped" for t in filled) / len(filled), 1),
        "avg_r": round(sum(rs) / len(rs), 3),
        "total_r": round(sum(rs), 2),
        "profit_factor": round(sum(wins) / -sum(losses), 2) if losses else None,
        "max_drawdown_r": round(dd, 2),
    }


def stats(trades: list[Trade]) -> dict:
    out = {"all": _summary(trades)}
    for g in ("A+", "A", "B"):
        out[g] = _summary([t for t in trades if t.grade == g])
    per = {}
    for name in sorted({s for t in trades for s in t.strategies}):
        per[name] = _summary([t for t in trades if name in t.strategies])
    out["by_strategy"] = per
    return out


def main() -> None:  # pragma: no cover - CLI
    from .data.providers import get_candles, load_csv

    p = argparse.ArgumentParser(description="Backtest the XAUUSD signal engine")
    p.add_argument("--provider", default=None)
    p.add_argument("--utc-offset", type=float, default=None,
                   help="hours the CSV time is ahead of UTC (MT5 broker time); default MT5_UTC_OFFSET")
    p.add_argument("--csv", default=None, help="CSV with time,open,high,low,close[,volume] in UTC")
    p.add_argument("--min-score", type=float, default=None)
    p.add_argument("--min-agree", type=int, default=None)
    p.add_argument("--ml", action="store_true", help="also filter with the trained ML model (models/meta_model.joblib)")
    a = p.parse_args()
    if a.utc_offset is None:
        from .config import settings

        a.utc_offset = settings.mt5_utc_offset if a.csv else 0.0
    df = load_csv(a.csv, a.utc_offset) if a.csv else get_candles(a.provider)
    cfg = EngineConfig()
    if a.min_score is not None:
        cfg.min_score = a.min_score
    if a.min_agree is not None:
        cfg.min_agree = a.min_agree
    meta = None
    if a.ml:
        from .ml import load

        meta = load()
        if meta is None:
            p.error("No trained model. Run: python -m backend.app.ml --csv your_data.csv")
        cfg.min_agree, cfg.min_score = meta.min_agree, meta.min_score
    res = run(df, cfg, meta)
    print(f"Data: {res['start']} -> {res['end']} ({res['bars']} bars of 15m)")
    if meta is not None:
        r = meta.report
        print("WARNING: if the ML model was trained on this same data, these results are far too optimistic.")
        print(f"  Honest result (period the model never saw, from {r.get('test_period_from')}):")
        print(f"  all candidates:    {r.get('test_all_candidates')}")
        print(f"  model-approved:    {r.get('test_model_approved')}")
    s = res["stats"]
    for k in ("all", "A+", "A", "B"):
        print(f"{k:>4}: {s[k]}")
    print("By strategy:")
    for name, v in s["by_strategy"].items():
        print(f"  {name:<18} {v}")


if __name__ == "__main__":  # pragma: no cover
    main()
