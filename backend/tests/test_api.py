import os

os.environ["DATA_PROVIDER"] = "synthetic"

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402

client = TestClient(app)  # not used as a context manager: no background network thread


def test_status():
    r = client.get("/api/status")
    assert r.status_code == 200
    assert len(r.json()["strategies"]) == 10


def test_candles_have_unix_seconds():
    r = client.get("/api/candles?tf=1h&limit=100")
    assert r.status_code == 200
    c = r.json()["candles"]
    assert len(c) == 100
    assert 1.5e9 < c[-1]["time"] < 2.5e9
    assert c[0]["time"] < c[-1]["time"]


def test_analysis_shape():
    r = client.get("/api/analysis")
    assert r.status_code == 200
    a = r.json()
    for key in ("regime", "votes", "blocked", "active_signal", "levels", "news_bias", "intermarket"):
        assert key in a


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "XAUUSD" in r.text
