from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings
from app.core.errors import LLMProviderError, LLMProviderUnavailableError
from app.llm.base import BaseLLMClient, LLMRequest, LLMResponse


class OllamaClient(BaseLLMClient):
    provider = "local"

    def __init__(self, settings: Settings) -> None:
        self.model = settings.ollama_model
        self._base_url = settings.ollama_base_url
        self._timeout_seconds = settings.llm_timeout_seconds
        self._context_tokens = settings.ollama_context_tokens
        self._batch_tokens = settings.ollama_batch_tokens

    async def complete(self, request: LLMRequest) -> LLMResponse:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                *[
                    {"role": message.role, "content": message.content}
                    for message in request.messages
                    if message.role != "system"
                ],
            ],
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
                "num_ctx": self._context_tokens,
                "num_batch": self._batch_tokens,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds, trust_env=False) as client:
                response = await client.post(f"{self._base_url}/api/chat", json=payload)
                response.raise_for_status()
        except httpx.ConnectError as exc:
            raise LLMProviderUnavailableError(
                f"Ollama is offline. Start Ollama and ensure {self.model} is installed."
            ) from exc
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise LLMProviderUnavailableError("Ollama request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            try:
                error_body = exc.response.json()
            except ValueError:
                error_body = {}
            detail = str(error_body.get("error", "")) if isinstance(error_body, dict) else ""
            if any(marker in detail.lower() for marker in (
                "failed to allocate", "unable to allocate", "out of memory",
                "requires more system memory",
            )):
                raise LLMProviderUnavailableError(
                    f"Ollama cannot load {self.model}: Windows does not have enough available "
                    "memory. Close unused applications and retry; if needed, enable "
                    "automatically managed Windows virtual memory."
                ) from exc
            message = f"Ollama returned HTTP {exc.response.status_code}."
            if detail:
                message += f" {detail[:500]}"
            raise LLMProviderError(message) from exc

        data: dict[str, Any] = response.json()
        message = data.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise LLMProviderError("Ollama returned an unexpected response shape.")

        return LLMResponse(
            provider=self.provider, model=self.model, content=message["content"].strip()
        )


async def list_ollama_models(settings: Settings) -> tuple[bool, list[str], str | None]:
    try:
        async with httpx.AsyncClient(timeout=3.0, trust_env=False) as client:
            response = await client.get(f"{settings.ollama_base_url}/api/tags")
            response.raise_for_status()
    except httpx.ConnectError:
        return False, [], "Ollama is offline."
    except httpx.TimeoutException:
        return False, [], "Ollama health check timed out."
    except httpx.HTTPStatusError as exc:
        return False, [], f"Ollama returned HTTP {exc.response.status_code}."

    data: dict[str, Any] = response.json()
    raw_models = data.get("models", [])
    model_names: list[str] = []
    if isinstance(raw_models, list):
        for item in raw_models:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                model_names.append(item["name"])

    return True, model_names, None
