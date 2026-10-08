from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["cloud", "local"]
AppEnvironment = Literal["local", "cloud"]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "The Lenny Growth Assistant"
    api_prefix: str = "/api"
    app_env: AppEnvironment = Field(default="local", validation_alias="APP_ENV")
    database_url: str = Field(default="", validation_alias="DATABASE_URL")

    # Separate 384-dimension cloud collection; the local Ollama collection is untouched.
    supabase_url: str = Field(default="", validation_alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(default="", validation_alias="SUPABASE_SERVICE_ROLE_KEY")
    cloud_vector_table: str = Field(default="transcript_chunks_cloud", validation_alias="CLOUD_VECTOR_TABLE")
    cloud_match_rpc: str = Field(default="match_transcript_chunks", validation_alias="CLOUD_MATCH_RPC")
    cloud_embedding_model: str = Field(default="BAAI/bge-small-en-v1.5", validation_alias="CLOUD_EMBEDDING_MODEL")
    fastembed_cache_dir: str = Field(
        default=str(Path(__file__).resolve().parents[2] / ".model-cache"),
        validation_alias="FASTEMBED_CACHE_DIR",
    )
    fastembed_threads: int = Field(default=2, validation_alias="FASTEMBED_THREADS", ge=1, le=16)
    fastembed_batch_size: int = Field(default=8, validation_alias="FASTEMBED_BATCH_SIZE", ge=1, le=64)
    fastembed_local_files_only: bool = Field(
        default=True, validation_alias="FASTEMBED_LOCAL_FILES_ONLY"
    )
    groq_api_key: str = Field(default="", validation_alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", validation_alias="GROQ_MODEL")
    cloud_llm_provider: Literal["openrouter", "groq"] = Field(
        default="openrouter", validation_alias="CLOUD_LLM_PROVIDER"
    )
    openrouter_api_key: str = Field(default="", validation_alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(
        default="nvidia/nemotron-3.5-lightning:free", validation_alias="OPENROUTER_MODEL"
    )
    cloud_qa_max_tokens: int = Field(
        default=1500, validation_alias="CLOUD_QA_MAX_TOKENS", ge=256, le=8192
    )

    cloud_provider: Literal["gemini", "openai"] = Field(
        default="gemini", validation_alias="CLOUD_PROVIDER"
    )
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-3.5-flash-lite", validation_alias="GEMINI_MODEL")
    gemini_embedding_api_key: str = Field(
        default="", validation_alias="GEMINI_EMBEDDING_API_KEY"
    )
    gemini_embedding_model: str = Field(
        default="gemini-embedding-001", validation_alias="GEMINI_EMBEDDING_MODEL"
    )
    gemini_embedding_dimensions: int = Field(
        default=768, validation_alias="GEMINI_EMBEDDING_DIMENSIONS", ge=128, le=3072
    )
    gemini_embedding_batch_size: int = Field(
        default=8, validation_alias="GEMINI_EMBEDDING_BATCH_SIZE", ge=1, le=32
    )
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", validation_alias="OPENAI_MODEL")

    ollama_base_url: str = Field(
        default="http://localhost:11434",
        validation_alias="OLLAMA_BASE_URL",
    )
    # llama3.2:3b is the CPU-friendly default. Set OLLAMA_MODEL in .env to
    # qwen3:4b (or another installed model) to override it.
    ollama_model: str = Field(default="llama3.2:3b", validation_alias="OLLAMA_MODEL")
    ollama_context_tokens: int = Field(
        default=4_096,
        validation_alias="OLLAMA_CONTEXT_TOKENS",
        ge=2_048,
        le=32_768,
    )
    ollama_batch_tokens: int = Field(
        default=64,
        validation_alias="OLLAMA_BATCH_TOKENS",
        ge=16,
        le=512,
    )
    ollama_embedding_model: str = Field(
        default="nomic-embed-text",
        validation_alias="OLLAMA_EMBEDDING_MODEL",
    )
    vector_collection_name: str = Field(
        default="lenny_podcast_transcripts",
        validation_alias="VECTOR_COLLECTION_NAME",
    )
    gemini_vector_collection_name: str = Field(
        # Legacy setting; cloud retrieval now uses a dedicated physical table.
        default="lenny_podcast_transcripts_gemini",
        validation_alias="GEMINI_VECTOR_COLLECTION_NAME",
    )
    rag_top_k: int = Field(default=5, validation_alias="RAG_TOP_K", ge=1, le=20)
    rag_min_cosine_similarity: float = Field(
        default=0.0,
        validation_alias="RAG_MIN_COSINE_SIMILARITY",
        ge=-1.0,
        le=1.0,
    )
    rag_context_max_chars: int = Field(
        default=6_000,
        validation_alias="RAG_CONTEXT_MAX_CHARS",
        ge=2_000,
        le=30_000,
    )
    transcripts_repo_url: str = Field(
        default="https://github.com/ChatPRD/lennys-podcast-transcripts",
        validation_alias="TRANSCRIPTS_REPO_URL",
    )
    transcripts_local_dir: str = Field(
        default="./data/lennys-podcast-transcripts",
        validation_alias="TRANSCRIPTS_LOCAL_DIR",
    )

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"],
        validation_alias="CORS_ORIGINS",
    )
    llm_timeout_seconds: float = Field(default=300.0, validation_alias="LLM_TIMEOUT_SECONDS")
    create_db_on_startup: bool = Field(default=False, validation_alias="CREATE_DB_ON_STARTUP")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("ollama_base_url")
    @classmethod
    def validate_ollama_base_url(cls, value: str) -> str:
        # Pydantic's AnyHttpUrl is used for validation while preserving str output.
        AnyHttpUrl(value)
        return value.rstrip("/")

    @property
    def is_cloud_configured(self) -> bool:
        if self.app_env == "cloud":
            key = self.groq_api_key if self.cloud_llm_provider == "groq" else self.openrouter_api_key
            return bool(key.strip())
        key = self.gemini_api_key if self.cloud_provider == "gemini" else self.openai_api_key
        return bool(key.strip())

    @property
    def cloud_model(self) -> str:
        if self.app_env == "cloud":
            return self.groq_model if self.cloud_llm_provider == "groq" else self.openrouter_model
        return self.gemini_model if self.cloud_provider == "gemini" else self.openai_model

    @property
    def is_cloud_rag_configured(self) -> bool:
        return bool(self.supabase_url.strip() and self.supabase_service_role_key.strip())

    def validate_cloud_model(self) -> None:
        from app.core.errors import ConfigurationError

        if self.cloud_llm_provider != "openrouter":
            raise ConfigurationError("Set CLOUD_LLM_PROVIDER=openrouter for cloud answers.")
        model = self.openrouter_model.strip()
        if not model or "/" not in model or any(char.isspace() for char in model):
            raise ConfigurationError("OPENROUTER_MODEL must be a full OpenRouter model ID: provider/model, optionally ending in :free.")
        if model.startswith("openrouter/"):
            raise ConfigurationError("Select an explicit provider/model instead of an automatic model router.")

    def validate_cloud_configuration(self) -> None:
        from app.core.errors import ConfigurationError

        self.validate_cloud_model()
        required = {
            "DATABASE_URL": self.database_url,
            "SUPABASE_URL": self.supabase_url,
            "SUPABASE_SERVICE_ROLE_KEY": self.supabase_service_role_key,
        }
        key_name = "GROQ_API_KEY" if self.cloud_llm_provider == "groq" else "OPENROUTER_API_KEY"
        required[key_name] = self.groq_api_key if self.cloud_llm_provider == "groq" else self.openrouter_api_key
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ConfigurationError("Missing cloud variables: " + ", ".join(missing))
        if not self.database_url.startswith("postgresql+asyncpg://"):
            raise ConfigurationError("DATABASE_URL must use the postgresql+asyncpg:// dialect.")
        try:
            AnyHttpUrl(self.supabase_url)
        except ValueError as exc:
            raise ConfigurationError("SUPABASE_URL must be your project's actual HTTPS URL, without placeholders.") from exc
        if self.cloud_embedding_model != "BAAI/bge-small-en-v1.5":
            raise ConfigurationError("Cloud RAG requires BAAI/bge-small-en-v1.5; model changes require re-ingestion.")

    @property
    def effective_gemini_embedding_api_key(self) -> str:
        return (self.gemini_embedding_api_key or self.gemini_api_key).strip()

    @property
    def is_database_configured(self) -> bool:
        return bool(self.database_url.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # An optional overlay allows cloud testing without changing the local .env.
    backend = Path(__file__).resolve().parents[2]
    env_file = os.getenv("APP_ENV_FILE")
    if env_file:
        overlay = Path(env_file)
        if not overlay.is_absolute():
            overlay = backend / overlay
        return Settings(_env_file=(backend / ".env", overlay))
    return Settings(_env_file=backend / ".env")
