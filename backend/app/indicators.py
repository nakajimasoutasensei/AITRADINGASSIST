"""Technical indicators. All are causal: the value at bar i only uses bars <= i."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rma(s: pd.Series, n: int) -> pd.Series:
    """Wilder's moving average."""
    return s.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["close"].shift(1)
    return pd.concat(
        [df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1
    ).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return rma(true_range(df), n)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = rma(d.clip(lower=0), n)
    down = rma(-d.clip(upper=0), n)
    rs = up / down.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    mid = close.rolling(n).mean()
    sd = close.rolling(n).std(ddof=0)
    return mid, mid + k * sd, mid - k * sd


def keltner(df: pd.DataFrame, n: int = 20, mult: float = 1.5):
    mid = ema(df["close"], n)
    a = atr(df, n)
    return mid, mid + mult * a, mid - mult * a


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = rma(true_range(df), n)
    plus_di = 100 * rma(pd.Series(plus_dm, index=df.index), n) / tr
    minus_di = 100 * rma(pd.Series(minus_dm, index=df.index), n) / tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return rma(dx.fillna(0), n)


def macd_hist(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    line = ema(close, fast) - ema(close, slow)
    return line - ema(line, signal)


def daily_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP that resets every UTC day. Falls back to a running mean price when volume is missing."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    day = df.index.floor("D")
    vol = df["volume"].fillna(0)
    if vol.sum() <= 0:
        return tp.groupby(day).expanding().mean().reset_index(level=0, drop=True)
    pv = (tp * vol).groupby(day).cumsum()
    cv = vol.groupby(day).cumsum().replace(0, np.nan)
    return (pv / cv).fillna(tp)


def swing_points(df: pd.DataFrame, k: int = 3) -> pd.DataFrame:
    """Confirmed swing highs/lows.

    A swing high at bar j (highest high of bars j-k..j+k) is only *known* at bar j+k.
    Returned columns describe, for each bar i, the most recent swings known at i:
      sh1, sh1_i  = last swing high price / bar position
      sh2, sh2_i  = the swing high before that
      sl1, sl1_i, sl2, sl2_i = same for swing lows
    """
    h = df["high"].to_numpy()
    lo = df["low"].to_numpy()
    n = len(df)
    out = np.full((n, 8), np.nan)
    sh = []  # (pos, price)
    sl = []
    for i in range(n):
        j = i - k
        if j >= k:
            win_h = h[j - k : j + k + 1]
            win_l = lo[j - k : j + k + 1]
            if h[j] == win_h.max() and (not sh or sh[-1][0] != j):
                sh.append((j, h[j]))
            if lo[j] == win_l.min() and (not sl or sl[-1][0] != j):
                sl.append((j, lo[j]))
        if sh:
            out[i, 0], out[i, 1] = sh[-1][1], sh[-1][0]
            if len(sh) > 1:
                out[i, 2], out[i, 3] = sh[-2][1], sh[-2][0]
        if sl:
            out[i, 4], out[i, 5] = sl[-1][1], sl[-1][0]
            if len(sl) > 1:
                out[i, 6], out[i, 7] = sl[-2][1], sl[-2][0]
    cols = ["sh1", "sh1_i", "sh2", "sh2_i", "sl1", "sl1_i", "sl2", "sl2_i"]
    return pd.DataFrame(out, index=df.index, columns=cols)
