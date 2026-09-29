from __future__ import annotations

import json

import httpx
import pytest

from football_prognoz.ai.ollama import LLMError, OllamaClient, think_for_model


def _client(handler, **kwargs) -> OllamaClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    defaults = {"model": "deepseek-v4.1-flash", "api_key": "secret"}
    defaults.update(kwargs)
    return OllamaClient(http=http, **defaults)  # type: ignore[arg-type]


def _ok(model: str, content: str = '{"summary": "ok"}') -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": model,
            "message": {"role": "assistant", "content": content},
            "done": True,
            "done_reason": "stop",
        },
    )


def test_chat_posts_native_payload_with_bearer_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _ok("deepseek-v4.1-flash")

    reply = _client(handler).chat("sys", "user")
    assert reply.text == '{"summary": "ok"}'
    assert reply.model == "deepseek-v4.1-flash"
    request = seen[0]
    assert str(request.url) == "https://ollama.com/api/chat"
    assert request.headers["Authorization"] == "Bearer secret"
    body = json.loads(request.content)
    assert body["model"] == "deepseek-v4.1-flash"
    assert body["stream"] is False
    assert body["think"] is False
    assert body["format"] == "json"
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["options"]["temperature"] == 0.2


def test_local_host_sends_no_authorization() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _ok("llama3")

    _client(handler, model="llama3", api_key="", host="http://127.0.0.1:11434/").chat("s", "u")
    assert str(seen[0].url) == "http://127.0.0.1:11434/api/chat"
    assert "Authorization" not in seen[0].headers
    assert "think" not in json.loads(seen[0].content)


def test_think_values_per_model_family() -> None:
    assert think_for_model("deepseek-v4.1-flash") is False
    assert think_for_model("gpt-oss:120b") == "low"
    assert think_for_model("gemma4:31b") is None


@pytest.mark.parametrize("status", [404, 502])
def test_fallback_model_used_once_on_404_or_502(status: int) -> None:
    models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        models.append(model)
        if model == "deepseek-v4.1-flash":
            return httpx.Response(status, json={"error": "model unavailable"})
        return _ok(model)

    reply = _client(handler, fallback_model="gpt-oss:120b").chat("s", "u")
    assert models == ["deepseek-v4.1-flash", "gpt-oss:120b"]
    assert reply.model == "gpt-oss:120b"


def test_no_fallback_on_auth_error() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(401, json={"error": "unauthorized"})

    with pytest.raises(LLMError, match="OLLAMA_API_KEY") as info:
        _client(handler, fallback_model="gpt-oss:120b").chat("s", "u")
    assert info.value.status_code == 401
    assert len(calls) == 1
    assert "secret" not in str(info.value)


def test_rate_limit_error_is_readable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "too many requests"})

    with pytest.raises(LLMError, match="429"):
        _client(handler).chat("s", "u")


def test_empty_content_and_error_field() -> None:
    def empty(request: httpx.Request) -> httpx.Response:
        return _ok("deepseek-v4.1-flash", content="  ")

    with pytest.raises(LLMError, match="пустой"):
        _client(empty).chat("s", "u")

    def errored(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "boom"})

    with pytest.raises(LLMError, match="boom"):
        _client(errored).chat("s", "u")


def test_network_error_does_not_retry_fallback() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(LLMError, match="Нет соединения"):
        _client(handler, fallback_model="gpt-oss:120b").chat("s", "u")
    assert len(calls) == 1
