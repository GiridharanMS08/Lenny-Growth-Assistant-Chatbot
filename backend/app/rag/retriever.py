from __future__ import annotations

import asyncio
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings
from app.core.errors import ConfigurationError
from app.rag.embeddings import build_embeddings, build_gemini_embeddings, to_sync_database_url


@dataclass(frozen=True)
class RetrievedChunk:
    content: str
    metadata: dict[str, Any]
    cosine_similarity: float


def _similarity_search_sync(query: str, top_k: int, provider: str) -> list[RetrievedChunk]:
    settings = get_settings()
    if settings.app_env == "cloud":
        from app.rag.cloud import match_chunks

        rows = match_chunks(settings, query, top_k)
        return [
            RetrievedChunk(
                content=str(row.get("content", "")),
                metadata=dict(row.get("metadata") or {}),
                cosine_similarity=float(row.get("similarity", 0.0)),
            )
            for row in rows
            if float(row.get("similarity", 0.0)) >= settings.rag_min_cosine_similarity
        ]
    if not settings.is_database_configured:
        raise ConfigurationError("DATABASE_URL is required for transcript retrieval.")

    if provider == "cloud":
        from app.rag.gemini_store import search

        rows = search(settings, build_gemini_embeddings(settings).embed_query(query), top_k)
        return [RetrievedChunk(document, dict(metadata or {}), float(score))
                for document, metadata, score in rows
                if score is not None and score >= settings.rag_min_cosine_similarity]

    try:
        from langchain_postgres import PGVector
        from langchain_postgres.vectorstores import DistanceStrategy
    except ImportError as exc:  # pragma: no cover - dependency setup guard
        raise ConfigurationError(
            "langchain-postgres is not installed. Run `pip install -e .` in backend/."
        ) from exc

    vector_store = PGVector(
        embeddings=build_embeddings(settings),
        collection_name=settings.vector_collection_name,
        connection=to_sync_database_url(settings.database_url),
        distance_strategy=DistanceStrategy.COSINE,
        use_jsonb=True,
    )
    scored_docs = vector_store.similarity_search_with_score(query=query, k=top_k)
    chunks: list[RetrievedChunk] = []
    for doc, cosine_distance in scored_docs:
        cosine_similarity = 1.0 - float(cosine_distance)
        if cosine_similarity < settings.rag_min_cosine_similarity:
            continue
        chunks.append(
            RetrievedChunk(
                content=doc.page_content,
                metadata=dict(doc.metadata),
                cosine_similarity=cosine_similarity,
            )
        )
    return chunks


async def retrieve_relevant_chunks(
    query: str, top_k: int | None = None, *, provider: str = "local"
) -> list[RetrievedChunk]:
    settings = get_settings()
    if not query.strip():
        return []
    resolved_top_k = settings.rag_top_k if top_k is None else top_k
    if not 1 <= resolved_top_k <= 20:
        raise ValueError("top_k must be between 1 and 20.")
    # The podcast name is common to every document and can dominate short queries.
    search_query = re.sub(
        r"^\s*what\s+(?:does|did)\s+lenny['\u2019]s\s+podcast\s+say\s+about\s+",
        "", query, flags=re.IGNORECASE,
    ).strip().rstrip("?").strip()
    candidates = await asyncio.to_thread(
        _similarity_search_sync, search_query or query.strip(), min(20, max(12, resolved_top_k * 3)), provider
    )
    return select_chunks(candidates, resolved_top_k)


def select_chunks(candidates: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
    """Keep cosine ranking, remove duplicates, and leave room for multiple episodes."""
    ranked = sorted(
        (chunk for chunk in candidates if chunk.content.strip() and math.isfinite(chunk.cosine_similarity)),
        key=lambda chunk: chunk.cosine_similarity, reverse=True,
    )
    unique: list[RetrievedChunk] = []
    seen: set[str] = set()
    for chunk in ranked:
        text = " ".join(chunk.content.split())
        if text not in seen:
            seen.add(text)
            unique.append(chunk)
    selected: list[RetrievedChunk] = []
    deferred: list[RetrievedChunk] = []
    counts: Counter[str] = Counter()
    for chunk in unique:
        source = str(chunk.metadata.get("source_path") or chunk.metadata.get("episode_title") or chunk.content)
        if counts[source] >= 2:
            deferred.append(chunk)
        else:
            selected.append(chunk)
            counts[source] += 1
    return (selected + deferred)[:top_k]


def prepare_context(chunks: list[RetrievedChunk], *, max_chars: int) -> list[RetrievedChunk]:
    """Pack complete passages; track exactly what the model is allowed to cite."""
    selected: list[RetrievedChunk] = []
    for chunk in chunks:
        if len(format_context([*selected, chunk])) <= max_chars:
            selected.append(chunk)
            continue
        # Cut only at paragraph/sentence boundaries, keeping the preceding context.
        header_size = len(format_context([RetrievedChunk("", chunk.metadata, chunk.cosine_similarity)]))
        room = max_chars - len(format_context(selected)) - header_size - (7 if selected else 0)
        prefix = chunk.content[:max(0, room)]
        boundary = max(prefix.rfind("\n\n"), prefix.rfind(". ") + 1, prefix.rfind("? ") + 1)
        if boundary >= 120:
            selected.append(RetrievedChunk(prefix[:boundary], chunk.metadata, chunk.cosine_similarity))
    return selected


def format_context(chunks: list[RetrievedChunk], *, max_chars: int | None = None) -> str:
    if not chunks:
        return ""

    formatted: list[str] = []
    remaining = max_chars
    for index, chunk in enumerate(chunks, start=1):
        title = chunk.metadata.get("episode_title", "Unknown episode")
        guest = chunk.metadata.get("guest_name", "Unknown guest")
        source = chunk.metadata.get("source_path", "unknown source")
        formatted_chunk = (
            f"[Chunk {index}]\n"
            f"Episode: {title}\n"
            f"Guest: {guest}\n"
            f"Source: {source}\n"
            f"Content:\n{chunk.content}"
        )
        if remaining is not None:
            if remaining <= 0:
                break
            formatted_chunk = formatted_chunk[:remaining]
            remaining -= len(formatted_chunk)
        formatted.append(formatted_chunk)
    return "\n\n---\n\n".join(formatted)


def format_sources(chunks: list[RetrievedChunk]) -> str:
    """Create a concise, de-duplicated source list for a user-facing answer."""
    sources: list[str] = []
    seen: set[tuple[str, str]] = set()
    for chunk in chunks:
        title = str(chunk.metadata.get("episode_title") or "Unknown episode")
        source = str(chunk.metadata.get("source_path") or "unknown source")
        key = (title, source)
        if key not in seen:
            seen.add(key)
            sources.append(f"- **{title}** — `{source}`")
    return "\n".join(sources)
