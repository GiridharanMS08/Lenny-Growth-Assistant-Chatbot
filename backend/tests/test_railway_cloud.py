from __future__ import annotations

import json

import groq
import httpx
import pytest
import supabase
from fastapi.testclient import TestClient

from app import main
from app.api.routes import models
from app.core.config import Settings
from app.core.errors import ConfigurationError, LLMProviderError
from app.llm.base import LLMMessage, LLMRequest
from app.llm.groq_client import GroqClient
from app.llm.openrouter_client import OpenRouterClient
from app.rag import cloud


def cloud_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **{
        "APP_ENV": "cloud", "CLOUD_LLM_PROVIDER": "openrouter",
        "OPENROUTER_API_KEY": "test-openrouter-secret",
        "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "test-service-secret",
        "GROQ_API_KEY": "test-groq-secret",
        **overrides,
    })


@pytest.mark.parametrize("provider,key_name", [("openrouter", "openrouter_api_key")])
def test_cloud_startup_validates_keys_and_warms_model(monkeypatch, provider, key_name) -> None:
    settings = cloud_settings(CLOUD_LLM_PROVIDER=provider, OPENROUTER_API_KEY="test-secret")
    warmed = []
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(models, "get_settings", lambda: settings)
    monkeypatch.setattr(cloud, "embed_query", lambda config, text: warmed.append(text) or [0.1] * 384)

    async def forbid_ollama(_):
        pytest.fail("Railway must not contact Ollama")

    monkeypatch.setattr(models, "list_ollama_models", forbid_ollama)
    with TestClient(main.create_app()) as client:
        assert client.get("/health").status_code == 200
        status = client.get("/api/models").json()
        assert status["cloud"]["provider"] == provider
        assert status["local"]["online"] is False
    assert warmed
    setattr(settings, key_name, "")
    with pytest.raises(ConfigurationError, match=key_name.upper()), TestClient(main.create_app()):
        pass


def test_supabase_sdk_rpc_uses_384_vectors_and_closes_http_client(monkeypatch) -> None:
    assert supabase.create_client
    settings = cloud_settings()
    original = httpx.Client
    clients = []

    def handler(request):
        assert request.url.path == "/rest/v1/rpc/match_transcript_chunks"
        assert request.headers["apikey"] == "test-service-secret"
        body = json.loads(request.content)
        assert len(body["query_embedding"]) == 384
        assert body["match_count"] == 3
        return httpx.Response(200, json=[{
            "id": "chunk-id", "content": "Activation evidence", "metadata": {}, "similarity": 0.8,
        }])

    def client(**kwargs):
        instance = original(transport=httpx.MockTransport(handler), **kwargs)
        clients.append(instance)
        return instance

    monkeypatch.setattr(cloud.httpx, "Client", client)
    monkeypatch.setattr(cloud, "embed_query", lambda config, query: [0.1] * 384)
    result = cloud.match_chunks(settings, "activation", 3)
    assert result[0]["content"] == "Activation evidence"
    assert clients[0].is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 401, 402, 403, 429])
async def test_openrouter_free_model_and_sanitized_errors(monkeypatch, status: int) -> None:
    original = httpx.AsyncClient

    def handler(request):
        assert request.url == "https://openrouter.ai/api/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-openrouter-secret"
        body = json.loads(request.content)
        assert body["model"] == "nvidia/nemotron-3.5-lightning:free"
        assert body["provider"]["max_price"] == {"prompt": 0, "completion": 0, "request": 0}
        assert body["provider"]["allow_fallbacks"] is False
        assert "models" not in body
        assert body["messages"][0]["content"] == "Use evidence"
        if status != 200:
            message = "Key limit exceeded (total limit)." if status == 403 else "test-openrouter-secret"
            return httpx.Response(status, json={"error": {"message": message}})
        return httpx.Response(200, json={"choices": [{
            "message": {"content": "Llama answer"}, "finish_reason": "stop",
        }]})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    client = OpenRouterClient(cloud_settings(OPENROUTER_API_KEY="test-openrouter-secret"))
    request = LLMRequest(system_prompt="Use evidence", messages=[LLMMessage(role="user", content="activation")])
    if status == 200:
        assert (await client.complete(request)).content == "Llama answer"
    else:
        with pytest.raises(LLMProviderError) as caught:
            await client.complete(request)
        assert "test-openrouter-secret" not in str(caught.value)
        if status == 403:
            assert "No paid model was tried" in str(caught.value)


@pytest.mark.parametrize("model", ["meta-llama/llama-3.3-70b-instruct", "openrouter/auto"])
def test_paid_models_rejected_before_network_call(model):
    with pytest.raises(ConfigurationError, match="Paid cloud models are disabled"):
        OpenRouterClient(cloud_settings(OPENROUTER_MODEL=model))


def test_unverified_cloud_provider_blocked():
    with pytest.raises(ConfigurationError, match="free-only"):
        cloud_settings(CLOUD_LLM_PROVIDER="groq").validate_free_cloud_model()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 401, 429])
async def test_groq_sdk_request_and_errors(monkeypatch, status: int) -> None:
    clients = []
    original = groq.AsyncGroq

    def handler(request):
        assert request.url.path == "/openai/v1/chat/completions"
        body = json.loads(request.content)
        assert body["messages"][0]["role"] == "system"
        assert len(body["messages"]) == 2
        assert body["max_tokens"] == 32
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "test-groq-secret"}})
        return httpx.Response(200, json={
            "id": "test", "object": "chat.completion", "created": 1, "model": body["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Evidence answer"}, "finish_reason": "stop"}],
        })

    def factory(**kwargs):
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        clients.append(client)
        return original(http_client=client, max_retries=0, **kwargs)

    monkeypatch.setattr(groq, "AsyncGroq", factory)
    client = GroqClient(cloud_settings())
    request = LLMRequest(system_prompt="Use evidence", messages=[LLMMessage(role="user", content="activation")], max_tokens=32)
    if status == 200:
        assert (await client.complete(request)).content == "Evidence answer"
    else:
        with pytest.raises(LLMProviderError) as caught:
            await client.complete(request)
        assert "test-groq-secret" not in str(caught.value)
    assert clients[0].is_closed
