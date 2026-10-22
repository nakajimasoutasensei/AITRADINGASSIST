import pandas as pd

from backend.app import backtest, ml
from backend.app.data.providers import synthetic
from backend.app.engine import EngineConfig


def test_train_save_load_and_filter(tmp_path):
    df = synthetic(days=200, seed=9, end=pd.Timestamp("2026-10-16 20:00", tz="UTC").to_pydatetime())
    path = tmp_path / "m.joblib"
    model = ml.train(df, path=path, min_rows=200)
    r = model.report
    assert r["candidates"] >= 200 and 0.4 <= r["threshold"] <= 0.8
    assert r["test_all_candidates"]["trades"] > 0
    loaded = ml.load(path)
    assert loaded is not None and loaded.feature_names == model.feature_names
    p = loaded.probability({n: 0.0 for n in loaded.feature_names})
    assert 0.0 <= p <= 1.0
    # the backtest with the model only keeps trades the model approves
    cfg = EngineConfig(min_agree=loaded.min_agree, min_score=loaded.min_score)
    res = backtest.run(df, cfg, loaded)
    assert res["stats"]["all"]["signals"] > 0


def test_not_enough_data_is_explained():
    df = synthetic(days=20, seed=1, end=pd.Timestamp("2026-10-16 20:00", tz="UTC").to_pydatetime())
    try:
        ml.train(df, path=None, min_rows=10_000)
    except ValueError as e:
        assert "more history" in str(e)
    else:
        raise AssertionError("expected ValueError")
