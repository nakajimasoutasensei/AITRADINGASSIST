"""Price data sources.

Every provider returns 15-minute candles as a DataFrame:
    index   = bar OPEN time, UTC, tz-aware
    columns = open, high, low, close, volume
Only fully closed bars are returned (the bar still forming is dropped).
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests

from ..config import settings

BASE_TF = pd.Timedelta(minutes=15)
COLUMNS = ["open", "high", "low", "close", "volume"]


class DataError(RuntimeError):
    pass


def _finalize(df: pd.DataFrame, now: datetime | None = None) -> pd.DataFrame:
    df = df[COLUMNS].astype(float)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["open", "high", "low", "close"])
    now = now or datetime.now(timezone.utc)
    # drop the bar that has not closed yet
    df = df[df.index + BASE_TF <= pd.Timestamp(now)]
    return df


# --------------------------------------------------------------------------- providers


def fetch_yfinance(symbol: str = "GC=F", days: int = 59) -> pd.DataFrame:
    """Free data from Yahoo Finance. GC=F is COMEX gold futures (close to spot XAUUSD)."""
    import yfinance as yf

    raw = yf.Ticker(symbol).history(interval="15m", period=f"{days}d", auto_adjust=False)
    if raw is None or raw.empty:
        raise DataError(f"yfinance returned no data for {symbol}")
    raw = raw.rename(columns=str.lower)
    raw.index = pd.DatetimeIndex(raw.index).tz_convert("UTC")
    return _finalize(raw)


def fetch_twelvedata(symbol: str = "XAU/USD", bars: int = 5000) -> pd.DataFrame:
    if not settings.twelvedata_api_key:
        raise DataError("TWELVEDATA_API_KEY is not set")
    r = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": symbol,
            "interval": "15min",
            "outputsize": bars,
            "timezone": "UTC",
            "apikey": settings.twelvedata_api_key,
        },
        timeout=20,
    )
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") != "ok":
        raise DataError(f"Twelve Data error: {payload.get('message', payload)}")
    df = pd.DataFrame(payload["values"])
    df.index = pd.to_datetime(df.pop("datetime")).dt.tz_localize("UTC")
    if "volume" not in df:
        df["volume"] = 0.0
    return _finalize(df)


def fetch_mt5(symbol: str | None = None, bars: int = 6000) -> pd.DataFrame:
    """Reads candles from a running MetaTrader 5 terminal (Windows only)."""
    try:
        import MetaTrader5 as mt5  # type: ignore
    except ImportError as e:  # pragma: no cover - Windows only
        raise DataError("MetaTrader5 package not installed (pip install MetaTrader5)") from e

    symbol = symbol or settings.mt5_symbol
    if not mt5.initialize():  # pragma: no cover
        raise DataError(f"MT5 initialize failed: {mt5.last_error()}")
    try:  # pragma: no cover
        mt5.symbol_select(symbol, True)
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, bars)
        if rates is None or len(rates) == 0:
            raise DataError(f"MT5 returned no data for {symbol}: {mt5.last_error()}")
        df = pd.DataFrame(rates)
        # MT5 timestamps are in broker server time
        idx = pd.to_datetime(df["time"], unit="s") - pd.Timedelta(hours=settings.mt5_utc_offset)
        df.index = pd.DatetimeIndex(idx).tz_localize("UTC")
        df["volume"] = df["tick_volume"]
        return _finalize(df)
    finally:  # pragma: no cover
        mt5.shutdown()


def load_csv(path: str) -> pd.DataFrame:
    """CSV with columns time/datetime/date, open, high, low, close[, volume]. Times assumed UTC."""
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    tcol = next((c for c in ("time", "datetime", "date", "timestamp", "gmt time") if c in df.columns), None)
    if tcol is None:
        raise DataError("CSV needs a time/datetime column")
    idx = pd.to_datetime(df.pop(tcol), utc=True, dayfirst="gmt time" == tcol)
    df.index = pd.DatetimeIndex(idx)
    if "volume" not in df:
        df["volume"] = 0.0
    df = df[COLUMNS].astype(float)
    # resample to 15m in case the CSV is 1m/5m
    agg = df.resample("15min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return _finalize(agg)


def synthetic(days: int = 120, seed: int = 7, start_price: float = 2400.0, end: datetime | None = None) -> pd.DataFrame:
    """Random but realistic-looking gold prices with trending and ranging periods. For offline tests."""
    rng = np.random.default_rng(seed)
    end = (end or datetime.now(timezone.utc)).replace(second=0, microsecond=0)
    end = end - timedelta(minutes=end.minute % 15)
    idx = pd.date_range(end=end, periods=days * 96, freq="15min", tz="UTC")
    idx = idx[idx.dayofweek < 5]  # no weekend bars
    n = len(idx)

    # regime-switching drift: trend up / trend down / range
    drift = np.zeros(n)
    i = 0
    while i < n:
        length = int(rng.integers(150, 600))
        drift[i : i + length] = rng.choice([0.00012, -0.00012, 0.0], p=[0.35, 0.3, 0.35])
        i += length
    hour = idx.hour.to_numpy()
    session_vol = np.where((hour >= 7) & (hour < 17), 1.5, 0.8)  # London/NY more volatile
    rets = drift + rng.standard_normal(n) * 0.0011 * session_vol
    # mean reversion inside ranges keeps range regimes range-bound
    close = np.empty(n)
    p = start_price
    anchor = p
    for k in range(n):
        if drift[k] == 0.0:
            rets[k] += -0.02 * (p - anchor) / anchor
        else:
            anchor = p
        p = p * (1 + rets[k])
        close[k] = p
    open_ = np.concatenate([[start_price], close[:-1]])
    wick = np.abs(rng.standard_normal((2, n))) * close * 0.0006 * session_vol
    high = np.maximum(open_, close) + wick[0]
    low = np.minimum(open_, close) - wick[1]
    vol = rng.integers(500, 3000, n) * session_vol
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)
    return _finalize(df, now=end + timedelta(minutes=15))


# --------------------------------------------------------------------------- cache

_cache: dict[str, tuple[float, pd.DataFrame]] = {}


def get_candles(provider: str | None = None, ttl: float = 60.0) -> pd.DataFrame:
    provider = (provider or settings.data_provider).lower()
    hit = _cache.get(provider)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    fetchers = {
        "yfinance": fetch_yfinance,
        "twelvedata": fetch_twelvedata,
        "mt5": fetch_mt5,
        "synthetic": synthetic,
    }
    if provider not in fetchers:
        raise DataError(f"Unknown DATA_PROVIDER '{provider}'. Use one of: {', '.join(fetchers)}")
    df = fetchers[provider]()
    if len(df) < 500:
        raise DataError(f"Not enough data from {provider}: {len(df)} bars")
    _cache[provider] = (time.time(), df)
    return df
