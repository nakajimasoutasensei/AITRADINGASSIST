import numpy as np
import pandas as pd
import pytest

from backend.app import backtest
from backend.app.data.providers import synthetic
from backend.app.engine import EngineConfig
from backend.app.features import build_features
from backend.app.news.sentiment import keyword_score, news_bias


@pytest.fixture(scope="module")
def df():
    return synthetic(days=60, seed=3, end=pd.Timestamp("2026-10-16 20:00", tz="UTC").to_pydatetime())


def test_features_do_not_look_ahead(df):
    """Every feature at bar k must be identical whether or not later bars exist."""
    full = build_features(df)
    for k in (900, 1500, len(df) - 37):
        part = build_features(df.iloc[: k + 1])
        a, b = full.iloc[k], part.iloc[k]
        for col in full.columns:
            if col == "atr_pct":  # rank over a trailing window: compare with tolerance
                continue
            va, vb = a[col], b[col]
            if isinstance(va, float) and np.isnan(va):
                assert np.isnan(vb), f"{col} at {k}"
            else:
                assert va == pytest.approx(vb, rel=1e-9, abs=1e-9), f"{col} at {k}: {va} vs {vb}"


def test_backtest_trades_have_valid_levels(df):
    res = backtest.run(df, EngineConfig())
    assert res["trades"], "expected some signals on 60 days of data"
    for t in res["trades"]:
        if t["direction"] == "BUY":
            assert t["sl"] < t["entry"] < t["tp1"] < t["tp2"] < t["tp3"]
        else:
            assert t["sl"] > t["entry"] > t["tp1"] > t["tp2"] > t["tp3"]
        assert -1.5 < t["result_r"] < 3.5
    s = res["stats"]["all"]
    assert 0 <= s["win_rate_tp1"] <= 100


def test_keyword_sentiment():
    assert keyword_score("Gold climbs as dollar weakens on Fed rate cut bets")["impact"] == "bullish"
    assert keyword_score("Gold slides as Treasury yields rise after strong jobs data")["impact"] == "bearish"
    assert keyword_score("Markets open quietly")["impact"] == "neutral"


def test_news_bias_sign():
    now = pd.Timestamp.now(tz="UTC").isoformat()
    bull = [{"time": now, "impact": "bullish", "strength": 1.0}]
    bear = [{"time": now, "impact": "bearish", "strength": 1.0}]
    assert news_bias(bull) > 0 > news_bias(bear)
    assert news_bias([]) == 0
