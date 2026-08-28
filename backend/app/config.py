from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent


def _resolve_env_file() -> str | None:
    """Use real .env files first, with .env.example as the local fallback."""
    candidates = (
        PROJECT_DIR / ".env",
        BACKEND_DIR / ".env",
        PROJECT_DIR / ".env.example",
        BACKEND_DIR / ".env.example",
    )
    return next((str(path) for path in candidates if path.exists()), None)


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = ""
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:1.7b"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    top_k: int = 3
    min_rerank_score: float = 0.25
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    artifact_max_chars: int = 100000
    transcript_dir: str = str(PROJECT_DIR / "data" / "transcripts")
    index_dir: str = str(PROJECT_DIR / "data" / "index")
    cors_origins: str = "http://localhost:5173"
    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_settings(self):
        if not self.database_url:
            raise ValueError(
                "DATABASE_URL is required. Set it in .env or .env.example."
            )
        if not self.database_url.lower().startswith(
            ("postgresql+psycopg://", "postgresql://")
        ):
            raise ValueError(
                "PostgreSQL is required. Use "
                "postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME."
            )

        for field_name in ("transcript_dir", "index_dir"):
            value = Path(getattr(self, field_name))
            if not value.is_absolute():
                setattr(self, field_name, str((PROJECT_DIR / value).resolve()))

        return self


settings = Settings()
