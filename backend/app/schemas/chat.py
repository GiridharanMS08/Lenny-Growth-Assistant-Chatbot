from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.session import MessageRead

LLMProvider = Literal["cloud", "local"]


class ChatRequest(BaseModel):
    session_id: uuid.UUID
    message: str = Field(min_length=1, max_length=20_000)
    active_llm: LLMProvider | None = None


class ChatResponse(BaseModel):
    session_id: uuid.UUID
    active_llm: LLMProvider
    skill: str
    message: MessageRead
