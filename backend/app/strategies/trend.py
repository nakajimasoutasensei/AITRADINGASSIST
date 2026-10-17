"""Trend and breakout strategies."""
from __future__ import annotations

from .base import BUY, SELL, Ctx, Vote, ok


def htf_trend(x: Ctx, i: int) -> int:
    """+1 if 4h and 1h both trend up, -1 if both down, else 0."""
    h4f, h4s, h1f, h1s, h1c = (x.v(c, i) for c in ("h4_ema50", "h4_ema200", "h1_ema20", "h1_ema50", "h1_close"))
    if not ok(h4f, h4s, h1f, h1s, h1c):
        return 0
    if h4f > h4s and h1f > h1s and h1c > h1s:
        return BUY
    if h4f < h4s and h1f < h1s and h1c < h1s:
        return SELL
    return 0


def trend_pullback(x: Ctx, i: int) -> Vote | None:
    """Multi-timeframe trend: 4h + 1h agree, enter on a 15m pullback to the EMA20/50 band."""
    trend = htf_trend(x, i)
    if trend == 0:
        return None
    o, h, l, c = (x.v(k, i) for k in ("open", "high", "low", "close"))
    e20, e50, atr = x.v("ema20", i), x.v("ema50", i), x.v("atr", i)
    if not ok(e20, e50, atr) or atr <= 0:
        return None
    band_lo, band_hi = min(e20, e50), max(e20, e50)
    if band_hi - band_lo < 0.3 * atr:
        mid = (band_hi + band_lo) / 2
        band_lo, band_hi = mid - 0.15 * atr, mid + 0.15 * atr
    adx_bonus = 0.15 if x.v("h4_adx", i) > 20 else 0.0
    if trend == BUY and e20 > e50 and l <= band_hi + 0.2 * atr and c > e50 and c > o:
        inv = min(band_lo - 0.5 * atr, x.v("sl1", i)) if ok(x.v("sl1", i)) else band_lo - 0.8 * atr
        return Vote("", BUY, band_lo, band_hi, inv, 0.55 + adx_bonus,
                    "4h + 1h uptrend, 15m pulled back to EMA20/50 and bounced")
    if trend == SELL and e20 < e50 and h >= band_lo - 0.2 * atr and c < e50 and c < o:
        inv = max(band_hi + 0.5 * atr, x.v("sh1", i)) if ok(x.v("sh1", i)) else band_hi + 0.8 * atr
        return Vote("", SELL, band_lo, band_hi, inv, 0.55 + adx_bonus,
                    "4h + 1h downtrend, 15m pulled back to EMA20/50 and rejected")
    return None


def session_breakout(x: Ctx, i: int) -> Vote | None:
    """Break of the Asian session range (00-07 UTC) during London / early New York."""
    hour = x.v("hour", i)
    if not (7 <= hour < 15) or i < 1:
        return None
    a_hi, a_lo, atr = x.v("asia_hi", i), x.v("asia_lo", i), x.v("atr", i)
    if not ok(a_hi, a_lo, atr) or atr <= 0:
        return None
    width = a_hi - a_lo
    if not (1.0 * atr <= width <= 8 * atr):
        return None
    c, pc = x.v("close", i), x.v("close", i - 1)
    mid = (a_hi + a_lo) / 2
    if c > a_hi + 0.1 * atr and pc <= a_hi:
        return Vote("", BUY, a_hi - 0.1 * atr, a_hi + 0.3 * atr, mid, 0.5,
                    f"Broke above Asian range high {a_hi:.2f}; buy the retest")
    if c < a_lo - 0.1 * atr and pc >= a_lo:
        return Vote("", SELL, a_lo - 0.3 * atr, a_lo + 0.1 * atr, mid, 0.5,
                    f"Broke below Asian range low {a_lo:.2f}; sell the retest")
    return None


def squeeze_breakout(x: Ctx, i: int) -> Vote | None:
    """Bollinger Bands inside Keltner Channels (squeeze), then expansion with momentum."""
    if i < 12:
        return None
    bbu, bbl, kcu, kcl = x["bb_up"], x["bb_lo"], x["kc_up"], x["kc_lo"]
    squeezed = sum(1 for k in range(i - 10, i) if bbu[k] < kcu[k] and bbl[k] > kcl[k])
    if squeezed < 6:
        return None
    c, atr, mid = x.v("close", i), x.v("atr", i), x.v("bb_mid", i)
    mh, pmh = x.v("macd_hist", i), x.v("macd_hist", i - 1)
    if not ok(c, atr, mid, mh, pmh):
        return None
    if c > bbu[i] and mh > 0 and mh > pmh:
        return Vote("", BUY, c - 0.6 * atr, c - 0.1 * atr, mid - 0.3 * atr, 0.5,
                    "Volatility squeeze released upward with rising momentum")
    if c < bbl[i] and mh < 0 and mh < pmh:
        return Vote("", SELL, c + 0.1 * atr, c + 0.6 * atr, mid + 0.3 * atr, 0.5,
                    "Volatility squeeze released downward with falling momentum")
    return None
