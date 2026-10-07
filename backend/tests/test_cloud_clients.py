from __future__ import annotations

import gzip
import json
from collections.abc import Callable

import httpx
import pytest
from pytest import MonkeyPatch

from app.api.routes import models
from app.core.config import Settings
from app.core.errors import ConfigurationError, LLMProviderError, LLMProviderUnavailableError
from app.llm import cloud_http, factory
from app.llm.base import LLMMessage, LLMRequest
from app.llm.gemini_client import GeminiClient
from app.llm.ollama_client import OllamaClient
from app.llm.openai_client import OpenAIClient


def use_transport(monkeypatch: MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]) -> None:
    original = httpx.AsyncClient
    monkeypatch.setattr(
        cloud_http.httpx, "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )


def request() -> LLMRequest:
    return LLMRequest(
        system_prompt="Use transcript evidence.",
        messages=[
            LLMMessage(role="system", content="Ignored duplicate system prompt"),
            LLMMessage(role="user", content="Activation?"),
            LLMMessage(role="assistant", content="Previous answer"),
            LLMMessage(role="user", content="Explain"),
        ],
        max_tokens=500,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["gemini", "openai"])
async def test_request_and_compressed_response(monkeypatch: MonkeyPatch, provider: str) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        assert req.headers["accept-encoding"] == "gzip, deflate"
        assert "test-secret" not in str(req.url)
        if provider == "gemini":
            assert req.url.host == "generativelanguage.googleapis.com"
            assert req.url.path.endswith("/models/gemini-test:generateContent")
            assert req.headers["x-goog-api-key"] == "test-secret"
            assert body["systemInstruction"]["parts"][0]["text"] == "Use transcript evidence."
            assert [m["role"] for m in body["contents"]] == ["user", "model", "user"]
            assert body["generationConfig"]["maxOutputTokens"] == 500
            payload = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
                {"thought": True, "text": "Hidden thought"}, {"text": "Answer"}, {"text": "More"},
            ]}}]}
        else:
            assert req.url == "https://api.openai.com/v1/responses"
            assert req.headers["authorization"] == "Bearer test-secret"
            assert body["model"] == "gpt-test"
            assert body["instructions"] == "Use transcript evidence."
            assert [m["role"] for m in body["input"]] == ["user", "assistant", "user"]
            assert body["max_output_tokens"] == 500
            assert body["store"] is False
            payload = {"status": "completed", "output": [
                {"type": "reasoning", "summary": []},
                {"type": "message", "content": [
                    {"type": "output_text", "text": "Answer"},
                    {"type": "output_text", "text": "More"},
                ]},
            ]}
        return httpx.Response(200, headers={"Content-Encoding": "gzip"}, content=gzip.compress(json.dumps(payload).encode()))

    use_transport(monkeypatch, handler)
    settings = Settings(_env_file=None, GEMINI_API_KEY="test-secret", OPENAI_API_KEY="test-secret", GEMINI_MODEL="gemini-test", OPENAI_MODEL="gpt-test")
    client = GeminiClient(settings) if provider == "gemini" else OpenAIClient(settings)
    response = await client.complete(request())
    assert response.content == "Answer\nMore"
    assert response.provider == "cloud"


@pytest.mark.parametrize("client_class,key_name", [(GeminiClient, "GEMINI_API_KEY"), (OpenAIClient, "OPENAI_API_KEY")])
def test_missing_key(client_class, key_name: str) -> None:
    with pytest.raises(ConfigurationError, match=key_name):
        client_class(Settings(_env_file=None, GEMINI_API_KEY="", OPENAI_API_KEY=""))


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["gemini", "openai"])
@pytest.mark.parametrize("status,message", [(400, "rejected the API key"), (401, "rejected the API key"), (403, "denied access"), (404, "model unavailable"), (429, "quota or rate limit"), (503, "temporarily unavailable")])
async def test_http_errors_do_not_expose_credentials(monkeypatch: MonkeyPatch, provider: str, status: int, message: str) -> None:
    use_transport(monkeypatch, lambda _: httpx.Response(status, json={"error": {"message": "Invalid API key: test-secret"}}))
    settings = Settings(_env_file=None, GEMINI_API_KEY="test-secret", OPENAI_API_KEY="test-secret")
    client = GeminiClient(settings) if provider == "gemini" else OpenAIClient(settings)
    with pytest.raises(LLMProviderError, match=message) as caught:
        await client.complete(request())
    assert "test-secret" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
async def test_network_errors(monkeypatch: MonkeyPatch, error) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise error("test-secret", request=req)
    use_transport(monkeypatch, handler)
    with pytest.raises(LLMProviderUnavailableError) as caught:
        await OpenAIClient(Settings(_env_file=None, OPENAI_API_KEY="test-secret")).complete(request())
    assert "test-secret" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("client_class,payload", [
    (GeminiClient, {"promptFeedback": {"blockReason": "SAFETY"}}),
    (GeminiClient, {"candidates": []}),
    (GeminiClient, {"candidates": [{"finishReason": "MAX_TOKENS"}]}),
    (OpenAIClient, {"status": "incomplete", "output": []}),
    (OpenAIClient, {"status": "completed", "output": []}),
    (OpenAIClient, {"output": [{"type": "message", "content": [{"type": "refusal"}]}]}),
])
async def test_empty_blocked_or_incomplete_answer(monkeypatch: MonkeyPatch, client_class, payload: dict) -> None:
    use_transport(monkeypatch, lambda _: httpx.Response(200, json=payload))
    with pytest.raises(LLMProviderError):
        await client_class(Settings(_env_file=None, GEMINI_API_KEY="test", OPENAI_API_KEY="test")).complete(request())


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,client_class", [("gemini", GeminiClient), ("openai", OpenAIClient)])
async def test_factory_and_status_follow_selected_provider(monkeypatch: MonkeyPatch, provider: str, client_class) -> None:
    settings = Settings(_env_file=None, CLOUD_PROVIDER=provider, GEMINI_API_KEY="gemini-secret", OPENAI_API_KEY="openai-secret")
    monkeypatch.setattr(factory, "get_settings", lambda: settings)
    monkeypatch.setattr(models, "get_settings", lambda: settings)
    async def offline(_):
        return False, [], "offline"
    monkeypatch.setattr(models, "list_ollama_models", offline)
    assert isinstance(factory.get_llm_client("cloud"), client_class)
    assert isinstance(factory.get_llm_client("local"), OllamaClient)
    status = await models.get_models()
    assert status.cloud.provider == provider
    assert status.cloud.model == settings.cloud_model
    assert status.cloud.configured is True
    assert "secret" not in status.model_dump_json()
    settings.gemini_api_key = "" if provider == "gemini" else settings.gemini_api_key
    settings.openai_api_key = "" if provider == "openai" else settings.openai_api_key
    assert (await models.get_models()).cloud.configured is False
    with pytest.raises(ConfigurationError):
        factory.get_llm_client("cloud")
