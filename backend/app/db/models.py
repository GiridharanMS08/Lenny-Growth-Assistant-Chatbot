from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

MessageRole = Literal["user", "assistant", "system"]
LLMProviderValue = Literal["cloud", "local"]


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""


class ChatSession(Base):
    """A persisted chat session."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    active_llm: Mapped[str] = mapped_column(String(length=16), nullable=False, default="local")

    messages: Mapped[list[Message]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Message.created_at",
    )


class Message(Base):
    """A persisted chat message belonging to a session."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(length=16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class TranscriptDocument(Base):
    """Episode-level metadata for ingested transcript sources."""

    __tablename__ = "transcript_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    episode_title: Mapped[str] = mapped_column(Text, nullable=False, default="Unknown episode")
    guest_name: Mapped[str] = mapped_column(Text, nullable=False, default="Unknown guest")
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    published_at: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    raw_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    chunks: Mapped[list[TranscriptChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="selectin"
    )


class TranscriptChunk(Base):
    """Metadata table for transcript chunks stored in pgvector by langchain-postgres."""

    __tablename__ = "transcript_chunks"
    __table_args__ = (Index("ix_transcript_chunks_document_chunk", "document_id", "chunk_index"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transcript_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped[TranscriptDocument] = relationship(back_populates="chunks")
