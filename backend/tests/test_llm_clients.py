from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from pytest import MonkeyPatch

from app.core.config import Settings
from app.core.errors import LLMProviderError, LLMProviderUnavailableError
from app.llm import ollama_client
from app.llm.base import LLMRequest


def use_ollama_transport(
    monkeypatch: MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        ollama_client.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )


@pytest.mark.asyncio
async def test_ollama_memory_error_has_actionable_message(monkeypatch: MonkeyPatch) -> None:
    use_ollama_transport(
        monkeypatch,
        lambda _: httpx.Response(500, json={"error": "unable to allocate CPU_REPACK buffer"}),
    )
    client = ollama_client.OllamaClient(Settings(_env_file=None, OLLAMA_MODEL="llama3.2:3b"))

    with pytest.raises(LLMProviderUnavailableError, match="enough available memory"):
        await client.complete(LLMRequest(system_prompt="Answer briefly."))


@pytest.mark.asyncio
async def test_ollama_preserves_other_server_error_details(monkeypatch: MonkeyPatch) -> None:
    use_ollama_transport(
        monkeypatch,
        lambda _: httpx.Response(404, json={"error": "model missing"}),
    )
    client = ollama_client.OllamaClient(Settings(_env_file=None))

    with pytest.raises(LLMProviderError, match="HTTP 404.*model missing"):
        await client.complete(LLMRequest(system_prompt="Answer briefly."))


@pytest.mark.asyncio
async def test_ollama_uses_configured_memory_budget_and_model(monkeypatch: MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "qwen3:1.7b"
        assert body["options"]["num_ctx"] == 4096
        assert body["options"]["num_batch"] == 64
        return httpx.Response(200, json={"message": {"content": "Working."}})

    use_ollama_transport(monkeypatch, handler)
    client = ollama_client.OllamaClient(
        Settings(
            _env_file=None,
            OLLAMA_MODEL="qwen3:1.7b",
            OLLAMA_CONTEXT_TOKENS=4096,
            OLLAMA_BATCH_TOKENS=64,
        )
    )
    response = await client.complete(LLMRequest(system_prompt="Answer briefly."))
    assert response.content == "Working."

