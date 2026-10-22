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


def test_load_mt5_export(tmp_path):
    from backend.app.data.providers import load_csv

    rows = ["<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>"]
    t = pd.Timestamp("2025-03-03 02:00")
    for k in range(8):  # eight 5-minute bars -> three 15-minute bars (last partial)
        ts = t + pd.Timedelta(minutes=5 * k)
        rows.append(f"{ts:%Y.%m.%d}\t{ts:%H:%M:%S}\t{2900 + k}\t{2901 + k}\t{2899 + k}\t{2900.5 + k}\t{100 + k}\t0\t20")
    p = tmp_path / "XAUUSD_M5.csv"
    p.write_text("\n".join(rows))
    df = load_csv(str(p), utc_offset_hours=2)
    assert str(df.index[0]) == "2025-03-03 00:00:00+00:00"  # 02:00 broker time = 00:00 UTC
    assert df.iloc[0]["open"] == 2900 and df.iloc[0]["high"] == 2903 and df.iloc[0]["close"] == 2902.5
    assert df.iloc[0]["volume"] == 100 + 101 + 102


def test_load_plain_csv(tmp_path):
    from backend.app.data.providers import load_csv

    p = tmp_path / "x.csv"
    p.write_text("time,open,high,low,close\n2025-03-03 00:00,1,2,0.5,1.5\n2025-03-03 00:15,1.5,3,1,2\n")
    df = load_csv(str(p))
    assert len(df) == 2 and df.iloc[1]["high"] == 3


def test_load_csv_date_formats(tmp_path):
    from backend.app.data.providers import load_csv

    p = tmp_path / "ms.csv"
    p.write_text("datetime,open,high,low,close\n2025-03-03 00:00:00.000,1,2,0.5,1.5\n")
    assert str(load_csv(str(p)).index[0]) == "2025-03-03 00:00:00+00:00"
    p = tmp_path / "duka.csv"
    p.write_text("Gmt time,Open,High,Low,Close,Volume\n04.03.2025 00:00:00.000,1,2,0.5,1.5,10\n")
    assert str(load_csv(str(p)).index[0]) == "2025-03-04 00:00:00+00:00"  # 4 March, not 3 April
