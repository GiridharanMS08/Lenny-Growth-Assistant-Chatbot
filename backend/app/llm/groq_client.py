from __future__ import annotations

from app.core.config import Settings
from app.core.errors import ConfigurationError, LLMProviderError, LLMProviderUnavailableError
from app.llm.base import BaseLLMClient, LLMRequest, LLMResponse


class GroqClient(BaseLLMClient):
    """Hosted Llama client used only when APP_ENV=cloud."""

    provider = "cloud"

    def __init__(self, settings: Settings) -> None:
        if not settings.groq_api_key.strip():
            raise ConfigurationError("GROQ_API_KEY is required when APP_ENV=cloud.")
        self.model = settings.groq_model
        self._api_key = settings.groq_api_key
        self._timeout_seconds = settings.llm_timeout_seconds

    async def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            from groq import APIConnectionError, APIStatusError, AsyncGroq, GroqError
        except ImportError as exc:  # pragma: no cover
            raise ConfigurationError("groq is not installed. Run pip install -r requirements.txt.") from exc
        try:
            async with AsyncGroq(api_key=self._api_key, timeout=self._timeout_seconds) as client:
                completion = await client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": request.system_prompt}, *[
                        {"role": message.role, "content": message.content}
                        for message in request.messages if message.role != "system"
                    ]],
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                )
        except APIConnectionError as exc:
            raise LLMProviderUnavailableError("Groq is unavailable or timed out.") from exc
        except APIStatusError as exc:
            if exc.status_code in {401, 403}:
                message = "Groq rejected the API key or its permissions."
            elif exc.status_code == 429:
                message = "Groq quota or rate limit reached."
            else:
                message = f"Groq returned HTTP {exc.status_code}. Check GROQ_MODEL and API access."
            raise LLMProviderError(message) from exc
        except GroqError as exc:
            raise LLMProviderError("Groq could not complete the request.") from exc
        content = completion.choices[0].message.content if completion.choices else None
        if not content:
            raise LLMProviderError("Groq returned no answer text.")
        return LLMResponse(provider=self.provider, model=self.model, content=content.strip())
