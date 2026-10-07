from __future__ import annotations

from app.core.config import LLMProvider, get_settings
from app.core.errors import ConfigurationError
from app.llm.base import BaseLLMClient
from app.llm.gemini_client import GeminiClient
from app.llm.ollama_client import OllamaClient
from app.llm.openai_client import OpenAIClient
from app.llm.openrouter_client import OpenRouterClient


def get_llm_client(provider: LLMProvider) -> BaseLLMClient:
    settings = get_settings()

    if provider == "cloud":
        if settings.app_env == "cloud":
            settings.validate_free_cloud_model()
            return OpenRouterClient(settings)
        if settings.cloud_provider == "gemini":
            return GeminiClient(settings)
        return OpenAIClient(settings)
    if provider == "local":
        return OllamaClient(settings)

    raise ConfigurationError(f"Unsupported LLM provider: {provider}")
