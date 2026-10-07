from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CloudModelStatus(BaseModel):
    provider: Literal["gemini", "openai", "groq", "openrouter"]
    configured: bool
    model: str


class LocalModelStatus(BaseModel):
    provider: str = "ollama"
    online: bool
    required_model: str
    available_models: list[str] = Field(default_factory=list)
    error: str | None = None


class ModelStatusResponse(BaseModel):
    cloud: CloudModelStatus
    local: LocalModelStatus
