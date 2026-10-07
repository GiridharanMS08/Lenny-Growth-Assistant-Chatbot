from __future__ import annotations

from app.core.config import Settings
from app.core.errors import ConfigurationError, LLMProviderError
from app.llm.base import BaseLLMClient, LLMRequest, LLMResponse
from app.llm.cloud_http import post_cloud_json


class OpenAIClient(BaseLLMClient):
    provider = "cloud"

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.openai_api_key.strip()
        if not self._api_key:
            raise ConfigurationError("OPENAI_API_KEY is not configured in backend/.env.")
        self.model = settings.openai_model.strip()
        self._timeout = settings.llm_timeout_seconds

    async def complete(self, request: LLMRequest) -> LLMResponse:
        data = await post_cloud_json(
            provider="OpenAI",
            url="https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {self._api_key}"},
            payload={
                "model": self.model,
                "instructions": request.system_prompt,
                "input": [
                    {"role": message.role, "content": message.content}
                    for message in request.messages if message.role != "system"
                ],
                "max_output_tokens": request.max_tokens,
                "store": False,
            },
            timeout=self._timeout,
        )
        if data.get("error") or data.get("status") not in (None, "completed"):
            raise LLMProviderError("OpenAI could not complete this answer. Try a shorter request.")
        output = data.get("output")
        if not isinstance(output, list):
            raise LLMProviderError("OpenAI returned an unexpected response.")
        texts: list[str] = []
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "refusal":
                    raise LLMProviderError("OpenAI declined this request. Try rephrasing it.")
                if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    texts.append(part["text"])
        text = "\n".join(texts).strip()
        if not text:
            raise LLMProviderError("OpenAI returned no answer text. Try a shorter request.")
        return LLMResponse(provider=self.provider, model=self.model, content=text)
