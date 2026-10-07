"""CPU embeddings and Supabase RPC retrieval for APP_ENV=cloud."""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any

import httpx

from app.core.config import Settings
from app.core.errors import ConfigurationError, LLMProviderError, LLMProviderUnavailableError

EXPECTED_DIMENSIONS = 384
_model_lock = Lock()


@lru_cache(maxsize=1)
def _embedding_model(model_name: str, cache_dir: str, threads: int, local_files_only: bool) -> Any:
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:  # pragma: no cover
        raise ConfigurationError("fastembed is not installed. Run pip install -r requirements.txt.") from exc
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    return TextEmbedding(
        model_name=model_name, cache_dir=cache_dir, threads=threads,
        local_files_only=local_files_only,
    )


def embedding_model(settings: Settings) -> Any:
    # functools.lru_cache alone can initialize twice on concurrent cache misses.
    with _model_lock:
        return _embedding_model(
            settings.cloud_embedding_model, settings.fastembed_cache_dir, settings.fastembed_threads,
            settings.fastembed_local_files_only,
        )


def _vector(values: Any) -> list[float]:
    vector = [float(value) for value in values]
    if len(vector) != EXPECTED_DIMENSIONS or not all(math.isfinite(value) for value in vector):
        raise LLMProviderError("Cloud embeddings must be finite 384-dimensional vectors.")
    return vector


def embed_documents(settings: Settings, texts: list[str]) -> list[list[float]]:
    vectors = [_vector(values) for values in embedding_model(settings).passage_embed(
        texts, batch_size=settings.fastembed_batch_size
    )]
    if len(vectors) != len(texts):
        raise LLMProviderError("FastEmbed did not return one vector per document.")
    return vectors


def embed_query(settings: Settings, query: str) -> list[float]:
    return _vector(next(iter(embedding_model(settings).query_embed(query))))


def match_chunks(settings: Settings, query: str, top_k: int) -> list[dict[str, Any]]:
    if not settings.is_cloud_rag_configured:
        raise ConfigurationError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required when APP_ENV=cloud.")
    try:
        from supabase import create_client
    except ImportError as exc:  # pragma: no cover
        raise ConfigurationError("supabase is not installed. Run pip install -r requirements.txt.") from exc
    vector = embed_query(settings, query)
    # Own the HTTP client so connections are closed even on failed RPC calls.
    try:
        from postgrest.exceptions import APIError

        from supabase import ClientOptions

        with httpx.Client(timeout=30.0, trust_env=False) as http_client:
            client = create_client(
                settings.supabase_url, settings.supabase_service_role_key,
                options=ClientOptions(httpx_client=http_client),
            )
            response = client.rpc(settings.cloud_match_rpc, {
                "query_embedding": vector,
                "match_count": top_k,
                "min_similarity": settings.rag_min_cosine_similarity,
            }).execute()
    except httpx.RequestError as exc:
        raise LLMProviderUnavailableError("Supabase retrieval is unavailable or timed out.") from exc
    except APIError as exc:
        raise LLMProviderError("Supabase retrieval failed. Check the cloud table, RPC, and permissions.") from exc
    if not isinstance(response.data, list):
        raise LLMProviderError("Supabase match RPC returned an unexpected response.")
    return [item for item in response.data if isinstance(item, dict)]
