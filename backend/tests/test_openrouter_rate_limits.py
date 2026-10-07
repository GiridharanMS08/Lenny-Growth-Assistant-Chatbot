from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import LLMProviderError
from app.llm.base import LLMMessage, LLMRequest
from app.llm.openrouter_client import OpenRouterClient, _rate_limit_message


@pytest.mark.parametrize(
    "error, expected",
    [
        (
            {"metadata": {"limit_source": "upstream_provider_shared_pool"}},
            "provider-capacity limit, not your daily account quota",
        ),
        ({"metadata": {"provider_error_code": "429"}}, "provider-capacity limit"),
        ({"metadata": {"provider_code": 429}}, "provider-capacity limit"),
        ({"message": "Model is temporarily rate-limited upstream"}, "provider-capacity limit"),
        ({"message": "Rate limit exceeded: free-models-per-day"}, "daily free-request limit"),
        ({"metadata": {"limit_source": "openrouter_free_daily"}}, "daily free-request limit"),
        ({"message": "Rate limit exceeded: free-models-per-min"}, "per-minute free-request limit"),
        ({"metadata": {"limit_source": "openrouter_per_minute"}}, "per-minute free-request limit"),
        ({"metadata": "unexpected upstream data"}, "daily quota may still be available"),
        ({}, "daily quota may still be available"),
    ],
)
def test_rate_limit_source(error, expected):
    assert expected in _rate_limit_message(httpx.Response(429), error)


@pytest.mark.parametrize("retry_after, expected", [("30", True), ("0", False), ("999999", False), ("secret", False)])
def test_retry_after_is_bounded_and_never_echoes_arbitrary_headers(retry_after, expected):
    response = httpx.Response(429, headers={"retry-after": retry_after})
    message = _rate_limit_message(response, {})
    assert ("Retry after 30 seconds" in message) is expected
    assert "secret" not in message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"error": {"message": "test-secret", "metadata": {
            "limit_source": "upstream_provider_shared_pool", "raw": "test-secret",
            "provider_name": "test-secret",
        }}},
        {"error": "test-secret"},
        {"error": None},
        ["test-secret"],
    ],
)
async def test_malformed_or_sensitive_error_bodies_are_safe(monkeypatch, payload):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(429, json=payload))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs))
    settings = Settings(_env_file=None, APP_ENV="cloud", OPENROUTER_API_KEY="test-secret")
    request = LLMRequest(system_prompt="Use evidence", messages=[LLMMessage(role="user", content="activation")])
    with pytest.raises(LLMProviderError) as caught:
        await OpenRouterClient(settings).complete(request)
    assert "test-secret" not in str(caught.value)
