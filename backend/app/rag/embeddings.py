from __future__ import annotations

import time
from typing import Any

import httpx
from langchain_core.embeddings import Embeddings

from app.core.config import Settings
from app.core.errors import ConfigurationError, LLMProviderError, LLMProviderUnavailableError


class GeminiEmbeddings(Embeddings):
    """Gemini embedding-001 adapter for both migration and cloud retrieval."""

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.effective_gemini_embedding_api_key
        if not self._api_key:
            raise ConfigurationError(
                "GEMINI_API_KEY or GEMINI_EMBEDDING_API_KEY is required for cloud RAG."
            )
        self.model = settings.gemini_embedding_model.removeprefix("models/")
        self.dimensions = settings.gemini_embedding_dimensions
        self._batch_size = settings.gemini_embedding_batch_size

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            requests = [
                {
                    "model": f"models/{self.model}",
                    "content": {"parts": [{"text": text}]},
                    "taskType": "RETRIEVAL_DOCUMENT",
                    "outputDimensionality": self.dimensions,
                }
                for text in batch
            ]
            data = self._post("batchEmbedContents", {"requests": requests})
            embeddings = data.get("embeddings")
            if not isinstance(embeddings, list) or len(embeddings) != len(batch):
                raise LLMProviderError("Gemini returned an unexpected batch embedding response.")
            for item in embeddings:
                values = item.get("values") if isinstance(item, dict) else None
                if not isinstance(values, list) or len(values) != self.dimensions:
                    raise LLMProviderError("Gemini returned an invalid embedding vector.")
                vectors.append([float(value) for value in values])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        data = self._post(
            "embedContent",
            {
                "model": f"models/{self.model}",
                "content": {"parts": [{"text": text}]},
                "taskType": "RETRIEVAL_QUERY",
                "outputDimensionality": self.dimensions,
            },
        )
        embedding = data.get("embedding")
        values = embedding.get("values") if isinstance(embedding, dict) else None
        if not isinstance(values, list) or len(values) != self.dimensions:
            raise LLMProviderError("Gemini returned an invalid query embedding vector.")
        return [float(value) for value in values]

    def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:{method}"
        try:
            response = None
            for attempt in range(3):
                response = httpx.post(
                    url,
                    headers={"x-goog-api-key": self._api_key},
                    json=payload,
                    timeout=120.0,
                    trust_env=False,
                )
                if response.status_code != 429 or attempt == 2:
                    break
                retry_after = response.headers.get("retry-after")
                try:
                    wait_seconds = max(1, min(120, int(retry_after or "60")))
                except ValueError:
                    wait_seconds = 60
                time.sleep(wait_seconds)
            assert response is not None
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise LLMProviderUnavailableError("Gemini embedding request timed out.") from exc
        except httpx.RequestError as exc:
            raise LLMProviderUnavailableError("Could not connect to Gemini embeddings.") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in {401, 403}:
                message = "Gemini rejected the embedding API key or its permissions."
            elif status == 429:
                message = "Gemini embedding quota or rate limit reached."
            else:
                message = f"Gemini embedding API returned HTTP {status}."
            raise LLMProviderError(message) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise LLMProviderError("Gemini returned an unexpected embedding response.")
        return data


def build_embeddings(settings: Settings) -> Any:
    """Build the embedding client lazily to keep app startup lightweight.

    The default uses Ollama `nomic-embed-text`. This keeps the project aligned with the
    local-first constraint and avoids introducing another paid embedding API.
    """
    try:
        from langchain_ollama import OllamaEmbeddings
    except ImportError as exc:  # pragma: no cover - dependency setup guard
        raise ConfigurationError(
            "langchain-ollama is not installed. Run `pip install -e .` in backend/."
        ) from exc

    return OllamaEmbeddings(
        model=settings.ollama_embedding_model,
        base_url=settings.ollama_base_url,
    )


def build_gemini_embeddings(settings: Settings) -> GeminiEmbeddings:
    return GeminiEmbeddings(settings)


def to_sync_database_url(database_url: str) -> str:
    """Convert SQLAlchemy asyncpg URLs into psycopg URLs for langchain-postgres."""
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url
