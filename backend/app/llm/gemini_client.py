from __future__ import annotations

from urllib.parse import quote

from app.core.config import Settings
from app.core.errors import ConfigurationError, LLMProviderError
from app.llm.base import BaseLLMClient, LLMRequest, LLMResponse
from app.llm.cloud_http import post_cloud_json


class GeminiClient(BaseLLMClient):
    provider = "cloud"

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.gemini_api_key.strip()
        if not self._api_key:
            raise ConfigurationError("GEMINI_API_KEY is not configured in backend/.env.")
        self.model = settings.gemini_model.removeprefix("models/").strip()
        self._timeout = settings.llm_timeout_seconds

    async def complete(self, request: LLMRequest) -> LLMResponse:
        data = await post_cloud_json(
            provider="Gemini",
            url=f"https://generativelanguage.googleapis.com/v1beta/models/{quote(self.model, safe='')}:generateContent",
            headers={"x-goog-api-key": self._api_key},
            payload={
                "systemInstruction": {"parts": [{"text": request.system_prompt}]},
                "contents": [
                    {
                        "role": "model" if message.role == "assistant" else "user",
                        "parts": [{"text": message.content}],
                    }
                    for message in request.messages if message.role != "system"
                ],
                "generationConfig": {"maxOutputTokens": request.max_tokens},
            },
            timeout=self._timeout,
        )
        feedback = data.get("promptFeedback")
        if isinstance(feedback, dict) and feedback.get("blockReason"):
            raise LLMProviderError("Gemini declined this prompt. Try rephrasing your request.")
        candidates = data.get("candidates")
        if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
            raise LLMProviderError("Gemini returned no answer. Try rephrasing your request.")
        candidate = candidates[0]
        if candidate.get("finishReason") == "MAX_TOKENS":
            raise LLMProviderError("Gemini reached the output limit. Try a shorter request.")
        if candidate.get("finishReason") not in (None, "STOP"):
            raise LLMProviderError("Gemini could not complete this answer. Try rephrasing your request.")
        content = candidate.get("content")
        parts = content.get("parts", []) if isinstance(content, dict) else []
        if not isinstance(parts, list):
            raise LLMProviderError("Gemini returned an unexpected response.")
        text = "\n".join(
            part["text"] for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str) and not part.get("thought")
        ).strip()
        if not text:
            raise LLMProviderError("Gemini returned no answer text. Try a shorter request.")
        return LLMResponse(provider=self.provider, model=self.model, content=text)
