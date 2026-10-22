import os

os.environ["DATA_PROVIDER"] = "synthetic"

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from backend.app import main  # noqa: E402
from backend.app.ai import analyst as an  # noqa: E402
from backend.app.data import providers  # noqa: E402

BUY_OK = {"action": "BUY", "zone_low": 99.0, "zone_high": 100.0, "sl": 97.5, "tp1": 101.5, "tp2": 103.0, "tp3": 105.0}


def test_validate_accepts_good_levels():
    assert an.validate(BUY_OK, price=100.5, atr=1.0) == []
    sell = {"action": "SELL", "zone_low": 100.0, "zone_high": 101.0, "sl": 102.5, "tp1": 99.0, "tp2": 97.5, "tp3": 96.0}
    assert an.validate(sell, price=99.8, atr=1.0) == []
    assert an.validate({"action": "NO_TRADE"}, 100, 1) == []


@pytest.mark.parametrize("change,problem", [
    ({"sl": 99.5}, "order"),              # stop inside the zone
    ({"tp1": 98.0}, "order"),             # TP below entry on a buy
    ({"sl": 90.0}, "stop distance"),      # stop far too wide
    ({"zone_low": 90.0, "zone_high": 91.0, "sl": 88.5, "tp1": 92.0}, "too far"),
])
def test_validate_rejects_bad_levels(change, problem):
    assert any(problem in p for p in an.validate({**BUY_OK, **change}, price=100.5, atr=1.0))


def _signal_df():
    """Synthetic data cut just after a bar where the engine gives a signal."""
    from backend.app import backtest
    df = providers.synthetic(days=90, seed=5, end=pd.Timestamp("2026-10-16 20:00", tz="UTC").to_pydatetime())
    res = backtest.run(df)
    t = next(t for t in reversed(res["trades"]) if t["fill_time"])
    cut = df.index.get_loc(pd.Timestamp(t["signal_time"]))
    return df.iloc[: cut + 1], t


@pytest.fixture
def fake_ai(monkeypatch, tmp_path):
    def install(verdict_fn):
        calls = []

        def caller(snapshot):
            calls.append(snapshot)
            return verdict_fn(snapshot)

        a = an.Analyst(path=tmp_path / "v.json", caller=caller)
        # run the "background" call synchronously for the test
        monkeypatch.setattr(an.threading, "Thread", lambda target, args, daemon: type("T", (), {"start": lambda self: target(*args)})())
        monkeypatch.setattr(main, "analyst", a)
        monkeypatch.setattr(type(a), "enabled", property(lambda self: True))
        df, trade = _signal_df()
        monkeypatch.setitem(providers._cache, "synthetic", (1e18, df))
        main._memo["key"] = None
        return calls, trade
    return install


def test_ai_adjusts_levels(fake_ai):
    def verdict(s):
        p = s["engine_proposal"]
        d = 1 if p["direction"] == "BUY" else -1
        e, risk = p["entry"], abs(p["entry"] - p["sl"]) * 1.1
        return {"action": p["direction"], "confidence": 70, "agrees_with_engine": True,
                "zone_low": round(e - 0.3, 2), "zone_high": round(e + 0.3, 2), "sl": round(e - d * risk, 2),
                "tp1": round(e + d * risk, 2), "tp2": round(e + 2 * d * risk, 2), "tp3": round(e + 3 * d * risk, 2),
                "summary": "ok", "reasons": ["trend"], "risks": [], "model": "fake", "tokens": {}}
    calls, trade = fake_ai(verdict)
    a = main.analysis()
    sig = a["active_signal"]
    assert len(calls) == 1
    snap = calls[0]
    assert snap["engine_proposal"]["direction"] == trade["direction"]
    assert len(snap["candles"]["m15_last_32"]) == 32
    assert sig["ai_status"] == "adjusted" and sig["open"]
    assert sig["engine_levels"]["sl"] != sig["sl"]
    # second refresh uses the saved verdict, no new call
    main.analysis()
    assert len(calls) == 1


def test_ai_rejects(fake_ai):
    calls, _ = fake_ai(lambda s: {"action": "NO_TRADE", "confidence": 20, "agrees_with_engine": False,
                                  "zone_low": 0, "zone_high": 0, "sl": 0, "tp1": 0, "tp2": 0, "tp3": 0,
                                  "summary": "mixed", "reasons": [], "risks": ["news"], "model": "fake", "tokens": {}})
    sig = main.analysis()["active_signal"]
    assert sig["ai_status"] == "rejected" and not sig["open"]


def test_ai_error_keeps_engine_signal(fake_ai):
    def boom(_):
        raise RuntimeError("network down")
    fake_ai(boom)
    sig = main.analysis()["active_signal"]
    assert sig["ai_status"] == "error" and sig["open"]
