"""Price-action / market-structure strategies (Smart Money Concepts style)."""
from __future__ import annotations

import math

from .base import BUY, SELL, Ctx, Vote, ok
from .trend import htf_trend


def structure_order_block(x: Ctx, i: int) -> Vote | None:
    """Break of structure (close beyond the last swing), then retest of the order block
    (the last opposite candle before the breakout move)."""
    o, h, l, c = x["open"], x["high"], x["low"], x["close"]
    sh, sl = x["sh1"], x["sl1"]
    atr = x.v("atr", i)
    if not ok(atr) or atr <= 0 or i < 30:
        return None
    trend = htf_trend(x, i)
    for j in range(i - 1, i - 21, -1):  # breakout happened in the last 20 bars
        # bullish break of structure at j
        if ok(sh[j - 1]) and c[j] > sh[j - 1] and c[j - 1] <= sh[j - 1]:
            ob = next((k for k in range(j, max(j - 12, 0), -1) if c[k] < o[k]), None)
            if ob is None:
                continue
            z_lo, z_hi = l[ob], max(o[ob], c[ob])
            if z_hi - z_lo > 2.5 * atr:
                continue
            touched_before = any(l[k] <= z_hi for k in range(j + 1, i))
            if not touched_before and l[i] <= z_hi and c[i] > z_lo:
                conf = 0.6 + (0.15 if trend == BUY else -0.15 if trend == SELL else 0)
                return Vote("", BUY, z_lo, z_hi, z_lo - 0.3 * atr, conf,
                            f"Bullish break of structure above {sh[j - 1]:.2f}, retest of order block")
            break
        # bearish break of structure at j
        if ok(sl[j - 1]) and c[j] < sl[j - 1] and c[j - 1] >= sl[j - 1]:
            ob = next((k for k in range(j, max(j - 12, 0), -1) if c[k] > o[k]), None)
            if ob is None:
                continue
            z_lo, z_hi = min(o[ob], c[ob]), h[ob]
            if z_hi - z_lo > 2.5 * atr:
                continue
            touched_before = any(h[k] >= z_lo for k in range(j + 1, i))
            if not touched_before and h[i] >= z_lo and c[i] < z_hi:
                conf = 0.6 + (0.15 if trend == SELL else -0.15 if trend == BUY else 0)
                return Vote("", SELL, z_lo, z_hi, z_hi + 0.3 * atr, conf,
                            f"Bearish break of structure below {sl[j - 1]:.2f}, retest of order block")
            break
    return None


def fair_value_gap(x: Ctx, i: int) -> Vote | None:
    """First return into an unfilled fair value gap (3-candle imbalance) from the last 30 bars."""
    h, l, c = x["high"], x["low"], x["close"]
    atr = x.v("atr", i)
    if not ok(atr) or atr <= 0 or i < 35:
        return None
    trend = htf_trend(x, i)
    for j in range(i - 2, i - 30, -1):
        # bullish gap: low of candle j above high of candle j-2
        gap_lo, gap_hi = h[j - 2], l[j]
        if gap_hi - gap_lo >= 0.3 * atr:
            first_touch = all(l[k] > gap_hi for k in range(j + 1, i))
            if first_touch and l[i] <= gap_hi and c[i] > gap_lo:
                conf = 0.5 + (0.15 if trend == BUY else -0.1 if trend == SELL else 0)
                return Vote("", BUY, gap_lo, gap_hi, min(l[j - 2], l[j - 1]) - 0.2 * atr, conf,
                            f"Price returned into bullish fair value gap {gap_lo:.2f}-{gap_hi:.2f}")
        # bearish gap: high of candle j below low of candle j-2
        gap_lo, gap_hi = h[j], l[j - 2]
        if gap_hi - gap_lo >= 0.3 * atr:
            first_touch = all(h[k] < gap_lo for k in range(j + 1, i))
            if first_touch and h[i] >= gap_lo and c[i] < gap_hi:
                conf = 0.5 + (0.15 if trend == SELL else -0.1 if trend == BUY else 0)
                return Vote("", SELL, gap_lo, gap_hi, max(h[j - 2], h[j - 1]) + 0.2 * atr, conf,
                            f"Price returned into bearish fair value gap {gap_lo:.2f}-{gap_hi:.2f}")
    return None


def liquidity_sweep(x: Ctx, i: int) -> Vote | None:
    """Stop hunt: wick through a known low/high (swing, previous day, Asian range) then close back inside."""
    o, h, l, c, atr = (x.v(k, i) for k in ("open", "high", "low", "close", "atr"))
    if not ok(atr) or atr <= 0:
        return None
    rng = h - l
    if rng <= 0:
        return None
    lows = {"swing low": x.v("sl1", i - 1), "previous day low": x.v("pd_low", i), "Asian low": x.v("asia_lo", i)}
    highs = {"swing high": x.v("sh1", i - 1), "previous day high": x.v("pd_high", i), "Asian high": x.v("asia_hi", i)}
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)
    for name, lvl in lows.items():
        if ok(lvl) and l < lvl and l > lvl - 1.5 * atr and c > lvl and lower_wick >= 0.5 * rng:
            conf = 0.6 + (0.1 if name != "swing low" else 0)
            return Vote("", BUY, lvl - 0.1 * atr, min(c, lvl + 0.5 * atr), l - 0.2 * atr, conf,
                        f"Swept liquidity below {name} {lvl:.2f} and closed back above")
    for name, lvl in highs.items():
        if ok(lvl) and h > lvl and h < lvl + 1.5 * atr and c < lvl and upper_wick >= 0.5 * rng:
            conf = 0.6 + (0.1 if name != "swing high" else 0)
            return Vote("", SELL, max(c, lvl - 0.5 * atr), lvl + 0.1 * atr, h + 0.2 * atr, conf,
                        f"Swept liquidity above {name} {lvl:.2f} and closed back below")
    return None


def round_levels(price: float) -> list[float]:
    """Gold reacts to $25 / $50 / $100 levels."""
    base = math.floor(price / 25) * 25
    return [base - 25, base, base + 25, base + 50]


def key_levels(x: Ctx, i: int) -> Vote | None:
    """Rejection candle at a round number or previous-day high/low."""
    o, h, l, c, atr = (x.v(k, i) for k in ("open", "high", "low", "close", "atr"))
    if not ok(atr) or atr <= 0 or h - l <= 0:
        return None
    levels = [(lv, f"round number {lv:.0f}") for lv in round_levels(c)]
    for col, name in (("pd_high", "previous day high"), ("pd_low", "previous day low"), ("pd_close", "previous day close")):
        if ok(x.v(col, i)):
            levels.append((x.v(col, i), name))
    rng = h - l
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)
    # support: wick touched the level, closed above it, bullish rejection
    sup = [(lv, n) for lv, n in levels if l <= lv + 0.2 * atr and l >= lv - 0.5 * atr and c > lv]
    if sup and c > o and lower_wick >= 0.4 * rng:
        lv = max(sup)[0]
        conf = 0.4 + 0.1 * min(len(sup), 3)
        names = ", ".join(n for _, n in sup)
        return Vote("", BUY, lv - 0.2 * atr, lv + 0.2 * atr, lv - 1.0 * atr, conf, f"Bullish rejection at {names}")
    res = [(lv, n) for lv, n in levels if h >= lv - 0.2 * atr and h <= lv + 0.5 * atr and c < lv]
    if res and c < o and upper_wick >= 0.4 * rng:
        lv = min(res)[0]
        conf = 0.4 + 0.1 * min(len(res), 3)
        names = ", ".join(n for _, n in res)
        return Vote("", SELL, lv - 0.2 * atr, lv + 0.2 * atr, lv + 1.0 * atr, conf, f"Bearish rejection at {names}")
    return None


def fib_confluence(x: Ctx, i: int) -> Vote | None:
    """Pullback into the 0.5-0.705 'golden zone' of the last impulse, in the direction of the trend."""
    trend = htf_trend(x, i)
    if trend == 0:
        return None
    sh, sh_i, sl, sl_i = x.v("sh1", i), x.v("sh1_i", i), x.v("sl1", i), x.v("sl1_i", i)
    o, l, h, c, atr = (x.v(k, i) for k in ("open", "low", "high", "close", "atr"))
    if not ok(sh, sl, atr) or atr <= 0:
        return None
    move = sh - sl
    if move < 2.5 * atr:
        return None
    if trend == BUY and sl_i < sh_i:  # impulse up: low then high
        z_lo, z_hi = sh - 0.705 * move, sh - 0.5 * move
        if l <= z_hi and c >= z_lo and c > o:
            return Vote("", BUY, z_lo, z_hi, sh - 0.886 * move, 0.5,
                        f"Pullback into 50-70.5% Fibonacci zone of the {sl:.2f}->{sh:.2f} rally")
    if trend == SELL and sh_i < sl_i:  # impulse down: high then low
        z_lo, z_hi = sl + 0.5 * move, sl + 0.705 * move
        if h >= z_lo and c <= z_hi and c < o:
            return Vote("", SELL, z_lo, z_hi, sl + 0.886 * move, 0.5,
                        f"Pullback into 50-70.5% Fibonacci zone of the {sh:.2f}->{sl:.2f} drop")
    return None
