"""Signal engine: regime detection + strategy ensemble + risk (zone, SL, TP, lot size)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import timedelta

import numpy as np
import pandas as pd

from .config import settings
from .strategies import BUY, SELL, STRATEGIES, Ctx, Vote
from .strategies.base import ok
from .strategies.price_action import round_levels


@dataclass
class EngineConfig:
    vote_ttl_bars: int = 4  # a strategy vote stays alive this many 15m bars
    min_agree: int = 2  # at least this many strategies must agree
    min_score: float = 50.0  # 0-100; below this no signal is shown
    zone_valid_bars: int = 8  # limit order in the zone expires after 2h
    min_risk_atr: float = 0.8
    max_risk_atr: float = 3.5
    sl_buffer_atr: float = 0.3
    tp_r: tuple = (1.0, 2.0, 3.0)
    spread: float = field(default_factory=lambda: settings.spread)


GRADES = [(80, "A+"), (65, "A"), (50, "B")]


def grade_for(score: float) -> str:
    for threshold, g in GRADES:
        if score >= threshold:
            return g
    return "C"


# --------------------------------------------------------------------------- regime


def regime(x: Ctx, i: int) -> str:
    atr_pct = x.v("atr_pct", i)
    if ok(atr_pct) and atr_pct > 0.97:
        return "volatile"
    adx, e20, e50, c = (x.v(k, i) for k in ("h1_adx", "h1_ema20", "h1_ema50", "h1_close"))
    if not ok(adx, e20, e50, c):
        return "range"
    if adx >= 22 and e20 > e50 and c > e50:
        return "trend_up"
    if adx >= 22 and e20 < e50 and c < e50:
        return "trend_down"
    return "range"


def regime_key(r: str) -> str:
    return "trend" if r.startswith("trend") else r


# --------------------------------------------------------------------------- votes


def votes_at(x: Ctx, i: int) -> list[Vote]:
    out = []
    for s in STRATEGIES:
        try:
            v = s.evaluate(x, i)
        except (IndexError, ValueError):
            v = None
        if v is not None:
            out.append(v)
    return out


def live_votes(x: Ctx, i: int, history: dict[int, list[Vote]], ttl: int) -> list[Vote]:
    """Most recent vote per strategy from the last `ttl` bars that is still valid at bar i."""
    c, atr = x.v("close", i), x.v("atr", i)
    latest: dict[str, Vote] = {}
    for b in range(max(0, i - ttl + 1), i + 1):
        for v in history.get(b, []):
            latest[v.strategy] = v
    alive = []
    for v in latest.values():
        if v.direction == BUY and (c <= v.invalidation or c > v.zone_high + 2 * atr):
            continue
        if v.direction == SELL and (c >= v.invalidation or c < v.zone_low - 2 * atr):
            continue
        alive.append(v)
    return alive


# --------------------------------------------------------------------------- filters


def time_block(ts: pd.Timestamp) -> str | None:
    wd, h = ts.weekday(), ts.hour
    if wd == 6:
        return "Sunday open: thin liquidity"
    if wd == 4 and h >= 19:
        return "Friday close: weekend gap risk"
    if 21 <= h < 23:
        return "Daily rollover: wide spreads"
    return None


def news_block(ts: pd.Timestamp, events: list[dict] | None, minutes: int = 30) -> str | None:
    for ev in events or []:
        t = pd.Timestamp(ev["time"])
        if abs((t - ts).total_seconds()) <= minutes * 60:
            return f"High-impact news: {ev.get('title', 'event')} at {t.strftime('%H:%M')} UTC"
    return None


# --------------------------------------------------------------------------- main decision


def _round_lot(lot: float) -> float:
    return max(0.01, math.floor(lot * 100) / 100)


def decide(
    x: Ctx,
    i: int,
    history: dict[int, list[Vote]],
    cfg: EngineConfig | None = None,
    news_bias: float = 0.0,
    intermarket_bias: float = 0.0,
    events: list[dict] | None = None,
) -> dict:
    cfg = cfg or EngineConfig()
    ts = x.index[i]
    reg = regime(x, i)
    rk = regime_key(reg)
    votes = live_votes(x, i, history, cfg.vote_ttl_bars)
    weights = {s.name: s.weights for s in STRATEGIES}

    def strength(direction: int) -> float:
        total = 0.0
        for v in votes:
            if v.direction != direction:
                continue
            w = weights[v.strategy][rk]
            if reg == "trend_up" and direction == SELL or reg == "trend_down" and direction == BUY:
                w *= 0.5  # counter-trend trades count less
            total += w * v.confidence
        return total

    s_buy, s_sell = strength(BUY), strength(SELL)
    direction = BUY if s_buy >= s_sell else SELL
    s_dir, s_opp = max(s_buy, s_sell), min(s_buy, s_sell)
    agreeing = [v for v in votes if v.direction == direction]
    opposing = [v for v in votes if v.direction != direction]

    score = 100 * (1 - math.exp(-s_dir / 1.5)) if s_dir > 0 else 0.0
    if s_dir > 0:
        score *= 1 - 0.6 * (s_opp / s_dir)
    notes = []
    for name, b in (("News", news_bias), ("Dollar & yields", intermarket_bias)):
        if b * direction <= -0.4:
            score *= 0.6
            notes.append(f"{name} bias is against this trade")
        elif b * direction >= 0.3:
            score = min(100, score * 1.1)
            notes.append(f"{name} bias supports this trade")

    result = {
        "time": ts.isoformat(),
        "price": x.v("close", i),
        "atr": x.v("atr", i),
        "regime": reg,
        "buy_strength": round(s_buy, 3),
        "sell_strength": round(s_sell, 3),
        "votes": [v.to_dict() for v in votes],
        "signal": None,
        "blocked": [],
        "notes": notes,
    }

    blocked = []
    if len(agreeing) < cfg.min_agree:
        blocked.append(f"Only {len(agreeing)} strategy(ies) agree (need {cfg.min_agree})")
    if score < cfg.min_score:
        blocked.append(f"Score {score:.0f} below {cfg.min_score:.0f}")
    if reg == "volatile":
        blocked.append("Extreme volatility: standing aside")
    for b in (time_block(ts + timedelta(minutes=15)), news_block(ts + timedelta(minutes=15), events)):
        if b:
            blocked.append(b)
    if blocked:
        result["blocked"] = blocked
        return result

    sig = build_trade(x, i, direction, agreeing, cfg)
    if sig is None:
        result["blocked"] = ["Stop loss would be too wide for this setup"]
        return result
    sig.update(
        score=round(score, 1),
        grade=grade_for(score),
        strategies=[v.strategy for v in agreeing],
        reasons=[v.reason for v in agreeing],
        against=[v.reason for v in opposing],
    )
    result["signal"] = sig
    return result


def build_trade(x: Ctx, i: int, direction: int, agreeing: list[Vote], cfg: EngineConfig) -> dict | None:
    atr, c = x.v("atr", i), x.v("close", i)
    lows = np.array([v.zone_low for v in agreeing])
    highs = np.array([v.zone_high for v in agreeing])
    conf = np.array([v.confidence for v in agreeing])

    # entry zone: overlap of the agreeing zones if it exists, else confidence-weighted average
    z_lo, z_hi = lows.max(), highs.min()
    if z_hi - z_lo < 0.15 * atr:
        z_lo = float(np.average(lows, weights=conf))
        z_hi = float(np.average(highs, weights=conf))
    mid = (z_lo + z_hi) / 2
    half = min(max((z_hi - z_lo) / 2, 0.1 * atr), 0.5 * atr)
    z_lo, z_hi = mid - half, mid + half

    # the zone must be at/below price for buys, at/above for sells
    if direction == BUY:
        z_hi = min(z_hi, c + 0.1 * atr)
        if z_lo >= z_hi:
            z_lo, z_hi = c - 0.3 * atr, c
    else:
        z_lo = max(z_lo, c - 0.1 * atr)
        if z_lo >= z_hi:
            z_lo, z_hi = c, c + 0.3 * atr
    entry = (z_lo + z_hi) / 2

    inv = float(np.median([v.invalidation for v in agreeing]))
    if direction == BUY:
        sl = min(inv, z_lo - cfg.sl_buffer_atr * atr) - cfg.spread
        risk = entry - sl
    else:
        sl = max(inv, z_hi + cfg.sl_buffer_atr * atr) + cfg.spread
        risk = sl - entry
    if risk < cfg.min_risk_atr * atr:
        risk = cfg.min_risk_atr * atr
        sl = entry - direction * risk
    if risk > cfg.max_risk_atr * atr:
        return None

    tps = [entry + direction * r * risk for r in cfg.tp_r]
    # pull TP1 in front of a nearby obstacle (swing / previous-day level / round number)
    if direction == BUY:
        obstacles = [x.v("sh1", i), x.v("pd_high", i)] + round_levels(entry)
        near = [o for o in obstacles if ok(o) and entry + 0.6 * risk < o < tps[0]]
        if near:
            tps[0] = min(near) - 0.05 * atr
    else:
        obstacles = [x.v("sl1", i), x.v("pd_low", i)] + round_levels(entry)
        near = [o for o in obstacles if ok(o) and tps[0] < o < entry - 0.6 * risk]
        if near:
            tps[0] = max(near) + 0.05 * atr

    risk_usd = settings.account_balance * settings.risk_percent / 100
    lot = _round_lot(risk_usd / (risk * settings.contract_size))
    valid_until = x.index[i] + timedelta(minutes=15 * (cfg.zone_valid_bars + 1))
    return {
        "direction": "BUY" if direction == BUY else "SELL",
        "zone_low": round(z_lo, 2),
        "zone_high": round(z_hi, 2),
        "entry": round(entry, 2),
        "sl": round(sl, 2),
        "tp1": round(tps[0], 2),
        "tp2": round(tps[1], 2),
        "tp3": round(tps[2], 2),
        "risk_per_oz": round(risk, 2),
        "rr_tp2": round(abs(tps[1] - entry) / risk, 2),
        "lot": lot,
        "risk_usd": round(lot * risk * settings.contract_size, 2),
        "valid_until": valid_until.isoformat(),
        "bar": i,
    }
