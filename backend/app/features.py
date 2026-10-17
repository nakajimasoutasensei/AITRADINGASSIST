"""Builds one feature table on the 15m timeframe, with 1h / 4h / daily context aligned
so that each row only contains information that was available when that 15m bar closed."""
from __future__ import annotations

import pandas as pd

from . import indicators as ta

BASE = pd.Timedelta(minutes=15)


def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return (
        df.resample(rule, label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["close"])
    )


def _align(htf: pd.DataFrame, base_index: pd.DatetimeIndex, tf: pd.Timedelta, prefix: str) -> pd.DataFrame:
    """Shift higher-timeframe rows to the 15m bar on which they become known (when the HTF bar closes)."""
    shifted = htf.copy()
    shifted.index = shifted.index + tf - BASE
    shifted = shifted.add_prefix(prefix)
    return shifted.reindex(base_index, method="ffill")


def _htf_block(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    h = _resample(df, rule)
    out = pd.DataFrame(index=h.index)
    out["close"] = h["close"]
    out["ema20"] = ta.ema(h["close"], 20)
    out["ema50"] = ta.ema(h["close"], 50)
    out["ema200"] = ta.ema(h["close"], 200)
    out["atr"] = ta.atr(h, 14)
    out["adx"] = ta.adx(h, 14)
    out["rsi"] = ta.rsi(h["close"], 14)
    return out


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    f = df.copy()
    c = f["close"]
    f["ema20"] = ta.ema(c, 20)
    f["ema50"] = ta.ema(c, 50)
    f["ema200"] = ta.ema(c, 200)
    f["atr"] = ta.atr(f, 14)
    f["atr_pct"] = f["atr"].rolling(500, min_periods=100).rank(pct=True)
    f["rsi"] = ta.rsi(c, 14)
    f["adx"] = ta.adx(f, 14)
    f["macd_hist"] = ta.macd_hist(c)
    f["bb_mid"], f["bb_up"], f["bb_lo"] = ta.bollinger(c, 20, 2.0)
    _, f["kc_up"], f["kc_lo"] = ta.keltner(f, 20, 1.5)
    f["vwap"] = ta.daily_vwap(f)
    f = f.join(ta.swing_points(f, k=3))

    # higher timeframes
    f = f.join(_align(_htf_block(df, "1h"), f.index, pd.Timedelta(hours=1), "h1_"))
    f = f.join(_align(_htf_block(df, "4h"), f.index, pd.Timedelta(hours=4), "h4_"))

    # previous day high / low (known from the start of the next day)
    d = _resample(df, "1D")
    prev = d[["high", "low", "close"]].shift(1).rename(columns=lambda x: f"pd_{x}")
    f = f.join(prev.reindex(f.index.floor("D")).set_axis(f.index))

    # Asian session range 00:00-07:00 UTC, known from 07:00 onward
    day = f.index.floor("D")
    hour = f.index.hour
    asia = f[hour < 7]
    a_hi = asia.groupby(asia.index.floor("D"))["high"].max()
    a_lo = asia.groupby(asia.index.floor("D"))["low"].min()
    known = hour >= 7
    f["asia_hi"] = pd.Series(a_hi.reindex(day).to_numpy(), index=f.index).where(known)
    f["asia_lo"] = pd.Series(a_lo.reindex(day).to_numpy(), index=f.index).where(known)

    f["hour"] = hour
    f["pos"] = range(len(f))
    return f
