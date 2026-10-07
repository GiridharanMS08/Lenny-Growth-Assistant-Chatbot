from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, Field

LLMProvider = Literal["cloud", "local"]
ChatRole = Literal["system", "user", "assistant"]


class LLMMessage(BaseModel):
    role: ChatRole
    content: str


class LLMRequest(BaseModel):
    system_prompt: str
    messages: list[LLMMessage] = Field(default_factory=list)
    temperature: float = 0.2
    max_tokens: int = 1_500


class LLMResponse(BaseModel):
    provider: LLMProvider
    model: str
    content: str


class BaseLLMClient(ABC):
    provider: LLMProvider
    model: str

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Return an assistant completion for a normalized chat request."""
