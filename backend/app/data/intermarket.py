"""Gold's main drivers: the US Dollar Index and US 10-year yield.
Falling dollar + falling yields = bullish for gold (and the opposite)."""
from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)
_cache: tuple[float, dict] | None = None


def _change(symbol: str) -> tuple[float, float] | None:
    import yfinance as yf

    h = yf.Ticker(symbol).history(interval="1h", period="5d", auto_adjust=False)
    if h is None or len(h) < 25:
        return None
    last = float(h["Close"].iloc[-1])
    day_ago = float(h["Close"].iloc[-25])
    return last, last - day_ago


def get_intermarket(ttl: float = 900) -> dict:
    global _cache
    if _cache and time.time() - _cache[0] < ttl:
        return _cache[1]
    out = {"bias": 0.0, "dxy": None, "dxy_change_pct": None, "us10y": None, "us10y_change": None, "ok": False}
    try:
        dxy = _change("DX-Y.NYB")
        tnx = _change("^TNX")
    except Exception as e:  # yfinance raises many different errors when offline
        log.warning("intermarket fetch failed: %s", e)
        dxy = tnx = None
    parts = []
    if dxy:
        pct = 100 * dxy[1] / (dxy[0] - dxy[1])
        out.update(dxy=round(dxy[0], 3), dxy_change_pct=round(pct, 3))
        parts.append((0.6, max(-1.0, min(1.0, -pct / 0.4))))
    if tnx:
        out.update(us10y=round(tnx[0], 3), us10y_change=round(tnx[1], 3))
        parts.append((0.4, max(-1.0, min(1.0, -tnx[1] / 0.08))))
    if parts:
        out["bias"] = round(sum(w * s for w, s in parts) / sum(w for w, _ in parts), 3)
        out["ok"] = True
    _cache = (time.time(), out)
    return out
