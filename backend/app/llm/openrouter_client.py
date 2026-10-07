"""OpenAI-compatible free-model chat API with zero-price routing."""

from __future__ import annotations

import httpx

from app.core.config import Settings
from app.core.errors import ConfigurationError, LLMProviderError, LLMProviderUnavailableError
from app.llm.base import BaseLLMClient, LLMRequest, LLMResponse


class OpenRouterClient(BaseLLMClient):
    provider = "cloud"

    def __init__(self, settings: Settings) -> None:
        if not settings.openrouter_api_key.strip():
            raise ConfigurationError("OPENROUTER_API_KEY is required for OpenRouter's free models.")
        settings.validate_free_cloud_model()
        self.model = settings.openrouter_model.strip()
        self._api_key = settings.openrouter_api_key.strip()
        self._timeout_seconds = settings.llm_timeout_seconds

    async def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds, trust_env=False) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": request.system_prompt},
                            *[{"role": item.role, "content": item.content} for item in request.messages if item.role != "system"],
                        ],
                        "temperature": request.temperature,
                        "max_tokens": request.max_tokens,
                        "stream": False,
                        "provider": {
                            "max_price": {"prompt": 0, "completion": 0, "request": 0},
                            "allow_fallbacks": False,
                        },
                    },
                )
                response.raise_for_status()
        except httpx.RequestError as exc:
            raise LLMProviderUnavailableError("OpenRouter is unavailable or timed out.") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            try:
                error_message = str(exc.response.json().get("error", {}).get("message", "")).lower()
            except (ValueError, AttributeError):
                error_message = ""
            if status == 403 and "key limit exceeded" in error_message:
                message = "OpenRouter blocked the free-model request with a key-limit restriction. No paid model was tried."
            elif status in {401, 403}:
                message = "OpenRouter rejected the API key or its permissions."
            elif status == 402:
                message = "OpenRouter rejected the free-model request. Paid models are disabled."
            elif status == 429:
                message = "OpenRouter free-model quota or rate limit reached. Retry later."
            elif status == 404:
                message = "The selected free model is unavailable. Choose an available :free model; paid fallback is disabled."
            else:
                message = f"OpenRouter returned HTTP {status}. Check OPENROUTER_MODEL and API access."
            raise LLMProviderError(message) from exc
        try:
            data = response.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError("OpenRouter returned an unexpected completion response.") from exc
        if choice.get("finish_reason") == "length":
            raise LLMProviderError("OpenRouter reached the output limit. Try a shorter request.")
        if not isinstance(content, str) or not content.strip():
            raise LLMProviderError("OpenRouter returned no answer text.")
        return LLMResponse(provider=self.provider, model=self.model, content=content.strip())
