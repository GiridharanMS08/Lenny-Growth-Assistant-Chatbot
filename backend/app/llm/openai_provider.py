from openai import OpenAI
from app.config import settings
from app.llm.base import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self):
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        self.client = OpenAI(api_key=settings.openai_api_key)

    def chat(self, messages, max_tokens=None):
        kwargs = {
            "model": settings.openai_model,
            "messages": messages,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        r = self.client.chat.completions.create(**kwargs)
        return r.choices[0].message.content or ""
