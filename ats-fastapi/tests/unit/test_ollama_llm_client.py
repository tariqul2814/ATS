"""Exercises the adapter against a mocked Ollama HTTP API (respx) — no real Ollama."""

import json

import httpx
import pytest
import respx

from app.adapters.ollama_llm_client import RESULT_SCHEMA, OllamaLlmClient
from app.config import OllamaSettings
from app.pipeline.errors import LlmTimeoutError, LlmUnavailableError

BASE = "http://ollama.test:11434"
MESSAGES = [{"role": "system", "content": "rules"}, {"role": "user", "content": "cv"}]


def client(**overrides) -> OllamaLlmClient:
    settings = OllamaSettings(base_url=BASE, **overrides)
    return OllamaLlmClient(settings, timeout_seconds=5)


def chat_reply(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "qwen2.5:3b",
            "created_at": "2026-10-30T00:00:00Z",
            "message": {"role": "assistant", "content": content},
            "done": True,
        },
    )


@respx.mock
async def test_returns_reply_and_sends_schema_and_options():
    route = respx.post(f"{BASE}/api/chat").mock(return_value=chat_reply('{"score": 1}'))
    assert await client().complete(MESSAGES) == '{"score": 1}'
    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == "qwen2.5:3b"
    assert sent["messages"] == MESSAGES
    assert sent["format"] == RESULT_SCHEMA
    assert "reportMarkdown" not in sent["format"]["properties"]  # rendered by the service
    assert "reportMarkdown" not in sent["format"]["required"]
    assert sent["options"] == {"temperature": 0.2, "num_ctx": 16384}
    assert sent["stream"] is False


@respx.mock
async def test_plain_json_mode_when_structured_output_off():
    route = respx.post(f"{BASE}/api/chat").mock(return_value=chat_reply("{}"))
    await client(structured_output=False).complete(MESSAGES)
    assert json.loads(route.calls.last.request.content)["format"] == "json"


@respx.mock
async def test_timeout_maps_to_llm_timeout():
    respx.post(f"{BASE}/api/chat").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(LlmTimeoutError) as err:
        await client().complete(MESSAGES)
    assert err.value.reason == "llm_timeout"


@respx.mock
async def test_connection_error_maps_to_unreachable():
    respx.post(f"{BASE}/api/chat").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(LlmUnavailableError) as err:
        await client().complete(MESSAGES)
    assert err.value.reason == "llm_unreachable"


@respx.mock
async def test_missing_model_maps_to_unreachable():
    respx.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(404, json={"error": "model 'qwen2.5:3b' not found"})
    )
    with pytest.raises(LlmUnavailableError, match="model not available"):
        await client().complete(MESSAGES)


@respx.mock
async def test_server_error_maps_to_unreachable():
    respx.post(f"{BASE}/api/chat").mock(return_value=httpx.Response(500, json={"error": "boom"}))
    with pytest.raises(LlmUnavailableError, match="HTTP 500"):
        await client().complete(MESSAGES)


@respx.mock
async def test_ready_when_model_listed():
    respx.get(f"{BASE}/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"model": "qwen2.5:3b", "name": "qwen2.5:3b"}]})
    )
    assert await client().check_ready()


@respx.mock
async def test_not_ready_when_model_missing_or_down():
    respx.get(f"{BASE}/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"model": "llama3:8b", "name": "llama3:8b"}]})
    )
    assert not await client().check_ready()
    respx.get(f"{BASE}/api/tags").mock(side_effect=httpx.ConnectError("refused"))
    assert not await client().check_ready()
