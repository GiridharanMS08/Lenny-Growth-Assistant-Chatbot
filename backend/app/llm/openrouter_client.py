"""OpenRouter chat for explicitly selected free or paid models."""

from __future__ import annotations

import httpx

from app.core.config import Settings
from app.core.errors import ConfigurationError, LLMProviderError, LLMProviderUnavailableError
from app.llm.base import BaseLLMClient, LLMRequest, LLMResponse


def _rate_limit_message(response: httpx.Response, error: dict[str, object], *, free: bool = True) -> str:
    """Classify 429s without exposing upstream messages, credentials, or prompts."""
    metadata = error.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    source = str(metadata.get("limit_source", "")).lower()
    detail = str(error.get("message", "")).lower()
    if (
        source.startswith("upstream_provider")
        or metadata.get("provider_error_code") is not None
        or metadata.get("provider_code") is not None
        or "rate-limited upstream" in detail
    ):
        message = (
            "The model's provider is temporarily rate-limited or overloaded. "
            "This is a provider-capacity limit, not your daily account quota. "
            "Retry later or choose another model."
        )
    elif "daily" in source or "free-models-per-day" in detail:
        quota = "free-request" if free else "request"
        message = f"OpenRouter's daily {quota} limit is reached. Wait for the daily quota to reset."
    elif "minute" in source or "free-models-per-min" in detail:
        quota = "free-request" if free else "request"
        message = f"OpenRouter's per-minute {quota} limit is reached. Wait before retrying."
    else:
        message = (
            "OpenRouter rate-limited the request. The response did not identify "
            "an account or provider limit; your daily quota may still be available. Retry later."
        )
    retry_after = response.headers.get("retry-after", "")
    if retry_after.isascii() and retry_after.isdigit() and len(retry_after) <= 5:
        seconds = int(retry_after)
        if 0 < seconds <= 86400:
            message += f" Retry after {seconds} seconds."
    return message


class OpenRouterClient(BaseLLMClient):
    provider = "cloud"

    def __init__(self, settings: Settings) -> None:
        if not settings.openrouter_api_key.strip():
            raise ConfigurationError("OPENROUTER_API_KEY is required for OpenRouter.")
        settings.validate_cloud_model()
        self.model = settings.openrouter_model.strip()
        self._free = self.model.endswith(":free")
        self._api_key = settings.openrouter_api_key.strip()
        self._timeout_seconds = settings.llm_timeout_seconds

    async def complete(self, request: LLMRequest) -> LLMResponse:
        provider: dict[str, object] = {"allow_fallbacks": False}
        if self._free:
            provider["max_price"] = {"prompt": 0, "completion": 0, "request": 0}
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                *[{"role": item.role, "content": item.content} for item in request.messages if item.role != "system"],
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
            "provider": provider,
        }
        if self.model in {"nvidia/nemotron-3.5-lightning:free", "deepseek/deepseek-v4.1-flash"}:
            # These endpoints support optional reasoning. Disable it so hidden
            # thinking does not consume the budget before an answer is produced.
            payload["reasoning"] = {"enabled": False}
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds, trust_env=False) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
                response.raise_for_status()
        except httpx.RequestError as exc:
            raise LLMProviderUnavailableError("OpenRouter is unavailable or timed out.") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            try:
                payload = exc.response.json()
            except ValueError:
                payload = {}
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            error = error if isinstance(error, dict) else {}
            error_message = str(error.get("message", "")).lower()
            if status == 403 and "key limit exceeded" in error_message:
                message = "OpenRouter blocked the request with a key-limit restriction."
                if self._free:
                    message += " No paid model was tried."
            elif status in {401, 403}:
                message = "OpenRouter rejected the API key or its permissions."
            elif status == 402:
                message = "OpenRouter requires sufficient account credits for the selected model. Check your account balance and key spending limit."
            elif status == 429:
                message = _rate_limit_message(exc.response, error, free=self._free)
            elif status == 404:
                message = "The selected model is unavailable. Check OPENROUTER_MODEL against the OpenRouter model catalog."
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
