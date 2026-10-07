from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LLMProvider = Literal["cloud", "local"]
MessageRole = Literal["user", "assistant", "system"]


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: MessageRole
    content: str
    created_at: datetime


class SessionCreate(BaseModel):
    active_llm: LLMProvider = "local"


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    active_llm: LLMProvider
    messages: list[MessageRead] = Field(default_factory=list)
