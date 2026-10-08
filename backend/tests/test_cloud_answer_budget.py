from __future__ import annotations

import json

import httpx
import pytest
from app.core.config import Settings
from app.llm.base import BaseLLMClient, LLMMessage, LLMProvider, LLMRequest, LLMResponse
from app.llm.openrouter_client import OpenRouterClient
from app.rag.retriever import RetrievedChunk
from app.skills import qa
from pydantic import ValidationError


class RecordingClient(BaseLLMClient):
    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self.model = "test-model"
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(provider=self.provider, model=self.model, content=json.dumps({"excerpts": [{"chunk": 1, "quote": "Choose an activation experience correlated with long-term retention."}]}))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "environment, provider, budget, expected",
    [
        ("cloud", "cloud", 1500, 1500),
        ("cloud", "cloud", 2500, 2500),
        ("local", "local", 1500, 1000),
        ("local", "cloud", 1500, 1000),
        ("cloud", "local", 1500, 1000),
    ],
)
async def test_qa_budget_changes_only_for_cloud_mode(monkeypatch, environment, provider, budget, expected):
    settings = Settings(_env_file=None, APP_ENV=environment, CLOUD_QA_MAX_TOKENS=budget)
    monkeypatch.setattr(qa, "get_settings", lambda: settings)

    async def retrieve(*args, **kwargs):
        return [RetrievedChunk(
            content="Choose an activation experience correlated with long-term retention.",
            metadata={"episode_title": "Activation Deep Dive", "source_path": "activation.md"},
            cosine_similarity=0.9,
        )]

    monkeypatch.setattr(qa, "retrieve_relevant_chunks", retrieve)
    client = RecordingClient(provider)
    answer = await qa.run_qa_skill(client, "How can I improve activation?")
    assert "correlated with long-term retention" in answer
    assert "**Sources**" in answer
    assert "**Activation Deep Dive** — `activation.md`" in answer
    assert client.requests[0].max_tokens == expected
    assert "correlated with long-term retention" in client.requests[0].messages[0].content


@pytest.mark.parametrize("budget", [0, 255, 8193])
def test_cloud_budget_is_bounded(budget):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, CLOUD_QA_MAX_TOKENS=budget)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model, disable_reasoning",
    [("nvidia/nemotron-3.5-lightning:free", True), ("google/gemma-4-31b-it:free", False)],
)
async def test_optional_reasoning_control_is_model_specific(monkeypatch, model, disable_reasoning):
    original = httpx.AsyncClient

    def handler(request):
        payload = json.loads(request.content)
        assert payload["max_tokens"] == 1500
        assert payload["provider"]["max_price"] == {"prompt": 0, "completion": 0, "request": 0}
        assert payload["provider"]["allow_fallbacks"] is False
        if disable_reasoning:
            assert payload["reasoning"] == {"enabled": False}
        else:
            assert "reasoning" not in payload
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "stop", "message": {"content": "Complete answer"},
        }]})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    settings = Settings(_env_file=None, APP_ENV="cloud", OPENROUTER_MODEL=model, OPENROUTER_API_KEY="test-key")
    request = LLMRequest(system_prompt="Use evidence", messages=[LLMMessage(role="user", content="activation")])
    assert (await OpenRouterClient(settings).complete(request)).content == "Complete answer"
