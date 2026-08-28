import httpx
from app.config import settings
from app.llm.base import LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(self):
        self.client = httpx.Client(timeout=180)

    def chat(self, messages, max_tokens=None):
        try:
            options = {
                "temperature": 0.3,
                "num_predict": max_tokens or 300,
            }
            r = self.client.post(
                f"{settings.ollama_base_url.rstrip('/')}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "messages": messages,
                    "stream": False,
                    "think": False,
                    "options": options,
                },
            )
            r.raise_for_status()
            return r.json()["message"]["content"].strip()
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Cannot reach Ollama at {settings.ollama_base_url}. "
                "Start Ollama and run: ollama pull " + settings.ollama_model
            ) from exc
