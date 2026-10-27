"""One interface for the AI providers: Claude (Anthropic) or DeepSeek.

complete_json(system, user, schema) returns a dict that matches `schema`.
  * Claude: structured outputs guarantee the schema.
  * DeepSeek: JSON mode only guarantees valid JSON, so the answer is checked and coerced against the
    schema here (missing fields / wrong types raise an error instead of being used).
"""
from __future__ import annotations

import json
import logging
import re

import requests

from ..config import settings

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


def provider() -> str | None:
    """Which AI is used: AI_PROVIDER, or automatically the one that has an API key (Claude first)."""
    p = settings.ai_provider
    if p == "claude":
        return "claude" if settings.anthropic_api_key else None
    if p == "deepseek":
        return "deepseek" if settings.deepseek_api_key else None
    if p == "auto":
        if settings.anthropic_api_key:
            return "claude"
        if settings.deepseek_api_key:
            return "deepseek"
    return None


def model_name() -> str | None:
    return {"claude": settings.claude_model, "deepseek": settings.deepseek_model}.get(provider() or "")


def complete_json(system: str, user: str, schema: dict, max_tokens: int = 8000) -> dict:
    p = provider()
    if p == "claude":
        return _claude(system, user, schema, max_tokens)
    if p == "deepseek":
        return _deepseek(system, user, schema, max_tokens)
    raise LLMError("No AI provider configured (set ANTHROPIC_API_KEY or DEEPSEEK_API_KEY)")


# ------------------------------------------------------------------ Claude


def _claude(system: str, user: str, schema: dict, max_tokens: int) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    try:
        response = client.beta.messages.create(
            model=settings.claude_model,
            max_tokens=max(max_tokens, 16000),
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": settings.claude_effort, "format": {"type": "json_schema", "schema": schema}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.APIError as e:
        raise LLMError(f"Claude API error: {e}") from e
    if response.stop_reason in ("refusal", "max_tokens"):
        raise LLMError(f"Claude stopped early ({response.stop_reason})")
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise LLMError("Claude returned no text")
    out = conform(json.loads(text), schema)
    out["_meta"] = {"provider": "claude", "model": response.model,
                    "tokens": {"in": response.usage.input_tokens, "out": response.usage.output_tokens}}
    return out


# ------------------------------------------------------------------ DeepSeek


def _schema_hint(schema: dict) -> str:
    """Plain description of the JSON shape for providers without schema enforcement."""
    def describe(s: dict) -> object:
        t = s.get("type")
        if t == "object":
            return {k: describe(v) for k, v in s["properties"].items()}
        if t == "array":
            return [describe(s["items"])]
        if "enum" in s:
            return " | ".join(str(e) for e in s["enum"])
        return t
    return json.dumps(describe(schema), indent=1)


def _deepseek(system: str, user: str, schema: dict, max_tokens: int) -> dict:
    sys_prompt = (system + "\n\nReply with a single JSON object only (no markdown), exactly in this shape "
                  "(all fields required):\n" + _schema_hint(schema))
    body = {
        "model": settings.deepseek_model,
        "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    url = settings.deepseek_base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.deepseek_api_key}", "Content-Type": "application/json"}
    last_error = "no answer"
    attempts = 0
    while attempts < 2:  # DeepSeek can occasionally return empty content: retry once
        attempts += 1
        try:
            r = requests.post(url, headers=headers, json=body, timeout=180)
        except requests.RequestException as e:
            raise LLMError(f"DeepSeek network error: {e}") from e
        if r.status_code == 400 and "response_format" in r.text and "response_format" in body:
            # some models (e.g. thinking models) may not accept JSON mode: ask again without it;
            # the prompt still asks for JSON and the answer is still checked against the schema
            body.pop("response_format")
            attempts -= 1
            continue
        if r.status_code != 200:
            detail = r.text[:300]
            hint = " (check DEEPSEEK_MODEL in .env)" if r.status_code in (400, 404) and "model" in detail.lower() else ""
            raise LLMError(f"DeepSeek API error {r.status_code}: {detail}{hint}")
        data = r.json()
        choice = (data.get("choices") or [{}])[0]
        if choice.get("finish_reason") == "length":
            raise LLMError("DeepSeek answer was cut off (max_tokens)")
        text = (choice.get("message") or {}).get("content") or ""
        if not text.strip():
            last_error = "empty answer"
            continue
        try:
            out = conform(_parse_json(text), schema)
        except (ValueError, LLMError) as e:
            last_error = f"bad JSON: {e}"
            continue
        usage = data.get("usage") or {}
        out["_meta"] = {"provider": "deepseek", "model": data.get("model", settings.deepseek_model),
                        "tokens": {"in": usage.get("prompt_tokens"), "out": usage.get("completion_tokens")}}
        return out
    raise LLMError(f"DeepSeek gave no usable answer ({last_error})")


def _parse_json(text: str) -> dict:
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


# ------------------------------------------------------------------ schema check


def conform(value, schema: dict, path: str = "$"):
    """Checks `value` against a (simple) JSON schema and coerces harmless differences
    (e.g. "3" -> 3, 2.0 -> 2). Raises LLMError when the answer cannot be used."""
    t = schema.get("type")
    if "enum" in schema:
        if isinstance(value, str) and t == "string":
            match = next((e for e in schema["enum"] if str(e).lower() == value.strip().lower()), None)
            if match is not None:
                return match
        if t == "integer":
            try:
                iv = int(float(value))
                if iv in schema["enum"]:
                    return iv
            except (TypeError, ValueError):
                pass
        if value in schema["enum"]:
            return value
        raise LLMError(f"{path}: {value!r} is not one of {schema['enum']}")
    if t == "object":
        if not isinstance(value, dict):
            raise LLMError(f"{path}: expected an object")
        out = {}
        for k, sub in schema["properties"].items():
            if k not in value:
                if k in schema.get("required", []):
                    raise LLMError(f"{path}.{k}: missing")
                continue
            out[k] = conform(value[k], sub, f"{path}.{k}")
        return out
    if t == "array":
        if not isinstance(value, list):
            raise LLMError(f"{path}: expected a list")
        return [conform(v, schema["items"], f"{path}[{i}]") for i, v in enumerate(value)]
    if t == "string":
        if isinstance(value, (dict, list)) or value is None:
            raise LLMError(f"{path}: expected text")
        return str(value)
    if t in ("number", "integer"):
        if isinstance(value, bool):
            raise LLMError(f"{path}: expected a number")
        try:
            num = float(value)
        except (TypeError, ValueError) as e:
            raise LLMError(f"{path}: expected a number") from e
        return int(round(num)) if t == "integer" else num
    if t == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        raise LLMError(f"{path}: expected true/false")
    return value
