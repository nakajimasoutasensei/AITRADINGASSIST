import dataclasses
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from backend.app.ai import analyst as an
from backend.app.ai import llm
from backend.app.config import settings
from backend.app.news import sentiment

# ---------------------------------------------------------------- schema check


def test_conform_coerces_small_differences():
    schema = {"type": "object", "required": ["a", "b", "c", "d"], "properties": {
        "a": {"type": "integer"}, "b": {"type": "string", "enum": ["BUY", "SELL"]},
        "c": {"type": "boolean"}, "d": {"type": "array", "items": {"type": "string"}}}}
    assert llm.conform({"a": "3", "b": "buy", "c": "true", "d": ["x"], "extra": 1}, schema) == \
        {"a": 3, "b": "BUY", "c": True, "d": ["x"]}


@pytest.mark.parametrize("bad", [
    {"b": "BUY", "c": True, "d": []},                 # missing field
    {"a": 1, "b": "HOLD", "c": True, "d": []},        # not in enum
    {"a": "x", "b": "BUY", "c": True, "d": []},       # not a number
    {"a": 1, "b": "BUY", "c": True, "d": "x"},        # not a list
])
def test_conform_rejects_unusable_answers(bad):
    schema = {"type": "object", "required": ["a", "b", "c", "d"], "properties": {
        "a": {"type": "integer"}, "b": {"type": "string", "enum": ["BUY", "SELL"]},
        "c": {"type": "boolean"}, "d": {"type": "array", "items": {"type": "string"}}}}
    with pytest.raises(llm.LLMError):
        llm.conform(bad, schema)


# ---------------------------------------------------------------- provider choice


def _use(monkeypatch, **kw):
    s = dataclasses.replace(settings, **kw)
    monkeypatch.setattr(llm, "settings", s)
    monkeypatch.setattr(an, "settings", s)
    return s


def test_provider_selection(monkeypatch):
    _use(monkeypatch, ai_provider="auto", anthropic_api_key="", deepseek_api_key="")
    assert llm.provider() is None
    _use(monkeypatch, ai_provider="auto", anthropic_api_key="", deepseek_api_key="d")
    assert llm.provider() == "deepseek"
    _use(monkeypatch, ai_provider="auto", anthropic_api_key="a", deepseek_api_key="d")
    assert llm.provider() == "claude"
    _use(monkeypatch, ai_provider="deepseek", anthropic_api_key="a", deepseek_api_key="d")
    assert llm.provider() == "deepseek"
    _use(monkeypatch, ai_provider="deepseek", anthropic_api_key="a", deepseek_api_key="")
    assert llm.provider() is None


# ---------------------------------------------------------------- DeepSeek against a fake server


class FakeDeepSeek(BaseHTTPRequestHandler):
    script: list = []  # list of (status, content) answers, consumed in order
    seen: list = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        FakeDeepSeek.seen.append({"path": self.path, "auth": self.headers.get("authorization"), "body": body})
        status, content = FakeDeepSeek.script.pop(0)
        if status == 200:
            out = {"model": body["model"], "choices": [{"message": {"role": "assistant", "content": content},
                                                        "finish_reason": "stop"}],
                   "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
        else:
            out = {"error": {"message": content}}
        data = json.dumps(out).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture
def deepseek(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), FakeDeepSeek)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    _use(monkeypatch, ai_provider="auto", anthropic_api_key="", deepseek_api_key="ds-key",
         deepseek_model="deepseek-test", deepseek_base_url=f"http://127.0.0.1:{srv.server_port}")
    FakeDeepSeek.seen.clear()
    yield FakeDeepSeek
    srv.shutdown()


VERDICT = {"action": "BUY", "confidence": "71", "agrees_with_engine": True, "zone_low": 99, "zone_high": 100,
           "sl": 97.5, "tp1": 101.5, "tp2": 103, "tp3": 105, "summary": "ok", "reasons": ["a"], "risks": [],
           "summary_id": "oke", "reasons_id": ["a"], "risks_id": []}


def test_deepseek_analyst_call(deepseek):
    deepseek.script = [(200, ""), (200, "```json\n" + json.dumps(VERDICT) + "\n```")]  # empty first, then fenced
    v = an.ask_ai({"price": 100})
    assert v["action"] == "BUY" and v["confidence"] == 71 and v["provider"] == "deepseek"
    assert v["summary_id"] == "oke"
    req = deepseek.seen[-1]
    assert req["path"] == "/chat/completions" and req["auth"] == "Bearer ds-key"
    assert req["body"]["model"] == "deepseek-test"
    assert req["body"]["response_format"] == {"type": "json_object"}
    assert "json" in req["body"]["messages"][0]["content"].lower()
    assert len(deepseek.seen) == 2  # retried once after the empty answer


def test_deepseek_bad_model_name_is_explained(deepseek):
    deepseek.script = [(400, "Model Not Exist")]
    with pytest.raises(llm.LLMError, match="DEEPSEEK_MODEL"):
        an.ask_ai({"price": 100})


def test_deepseek_incomplete_answer_is_rejected(deepseek):
    broken = {k: v for k, v in VERDICT.items() if k != "sl"}
    deepseek.script = [(200, json.dumps(broken)), (200, json.dumps(broken))]
    with pytest.raises(llm.LLMError, match="sl"):
        an.ask_ai({"price": 100})


def test_deepseek_scores_news(deepseek, monkeypatch):
    items = {"items": [{"id": "h1", "impact": "bearish", "strength": 2, "event_risk": "low", "reason": "yields up",
                        "reason_id": "yield naik"}]}
    deepseek.script = [(200, json.dumps(items))]
    monkeypatch.setattr(sentiment, "_seen", {})
    out = sentiment.analyze([{"id": "h1", "title": "Yields jump", "time": "2026-10-20T10:00:00+00:00"}])
    assert out[0]["impact"] == "bearish" and out[0]["model"] == "deepseek"
    assert out[0]["reason_id"] == "yield naik"
    assert out[0]["strength"] == pytest.approx(2 / 3)


def test_deepseek_without_json_mode_support(deepseek):
    deepseek.script = [(400, "response_format type json_object is not supported for this model"),
                       (200, json.dumps(VERDICT))]
    v = an.ask_ai({"price": 100})
    assert v["action"] == "BUY"
    assert "response_format" in deepseek.seen[0]["body"] and "response_format" not in deepseek.seen[1]["body"]


def test_default_deepseek_model():
    from backend.app.config import Settings
    import os
    if "DEEPSEEK_MODEL" not in os.environ:
        assert Settings().deepseek_model == "deepseek-flash"
