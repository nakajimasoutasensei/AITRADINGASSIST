"""Mean-reversion and exhaustion strategies (best in ranging markets)."""
from __future__ import annotations

from .base import BUY, SELL, Ctx, Vote, ok


def mean_reversion(x: Ctx, i: int) -> Vote | None:
    """Close back inside the Bollinger Band after an RSI extreme, only when the 1h trend is weak."""
    if i < 2:
        return None
    if x.v("h1_adx", i) >= 22:
        return None
    c, pc, l, h, atr = x.v("close", i), x.v("close", i - 1), x.v("low", i), x.v("high", i), x.v("atr", i)
    bbl, pbbl, bbu, pbbu = x.v("bb_lo", i), x.v("bb_lo", i - 1), x.v("bb_up", i), x.v("bb_up", i - 1)
    prsi = min(x.v("rsi", i - 1), x.v("rsi", i - 2))
    prsi_hi = max(x.v("rsi", i - 1), x.v("rsi", i - 2))
    if not ok(c, pc, atr, bbl, pbbl, bbu, pbbu) or atr <= 0:
        return None
    if pc < pbbl and c > bbl and prsi < 30:
        return Vote("", BUY, l, max(c, l + 0.3 * atr), l - 0.5 * atr, 0.55,
                    "Oversold (RSI < 30) below lower Bollinger Band, closed back inside; target VWAP / mid-band")
    if pc > pbbu and c < bbu and prsi_hi > 70:
        return Vote("", SELL, min(c, h - 0.3 * atr), h, h + 0.5 * atr, 0.55,
                    "Overbought (RSI > 70) above upper Bollinger Band, closed back inside; target VWAP / mid-band")
    return None


def rsi_divergence(x: Ctx, i: int) -> Vote | None:
    """Price makes a lower low / higher high but RSI does not. Fires when the new swing is confirmed."""
    rsi, atr, c = x["rsi"], x.v("atr", i), x.v("close", i)
    if not ok(atr) or atr <= 0:
        return None
    sl1, sl1_i, sl2, sl2_i = x.v("sl1", i), x.v("sl1_i", i), x.v("sl2", i), x.v("sl2_i", i)
    if ok(sl1, sl2) and sl1_i == i - 3 and 5 <= sl1_i - sl2_i <= 60:
        if sl1 < sl2 and rsi[int(sl1_i)] > rsi[int(sl2_i)] + 3 and c - sl1 < 1.5 * atr:
            return Vote("", BUY, sl1, sl1 + 0.6 * atr, sl1 - 0.4 * atr, 0.5,
                        f"Bullish RSI divergence: lower low {sl1:.2f} with higher RSI")
    sh1, sh1_i, sh2, sh2_i = x.v("sh1", i), x.v("sh1_i", i), x.v("sh2", i), x.v("sh2_i", i)
    if ok(sh1, sh2) and sh1_i == i - 3 and 5 <= sh1_i - sh2_i <= 60:
        if sh1 > sh2 and rsi[int(sh1_i)] < rsi[int(sh2_i)] - 3 and sh1 - c < 1.5 * atr:
            return Vote("", SELL, sh1 - 0.6 * atr, sh1, sh1 + 0.4 * atr, 0.5,
                        f"Bearish RSI divergence: higher high {sh1:.2f} with lower RSI")
    return None
