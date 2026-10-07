"""Ingest local transcripts with CPU FastEmbed into the isolated cloud pgvector table.

This intentionally does not call Ollama and does not modify ingest_transcripts.py.
Run from the repository root: python scripts/ingest_supabase_cloud.py
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import psycopg
from langchain_text_splitters import RecursiveCharacterTextSplitter

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import Settings  # noqa: E402
from app.core.errors import ConfigurationError  # noqa: E402
from app.rag.cloud import embed_documents, embedding_model  # noqa: E402
from app.rag.embeddings import to_sync_database_url  # noqa: E402
from ingest_transcripts import _stable_chunk_id, _transcript_documents  # noqa: E402

logger = logging.getLogger("cloud_transcript_ingestion")
CHUNK_SIZE_TOKENS = 480
CHUNK_OVERLAP_TOKENS = 80
BATCH_SIZE = 64
T = TypeVar("T")


def _database_operation(settings: Settings, operation: Callable[[psycopg.Connection], T]) -> T:
    """Retry transient connection failures; each upsert batch is transactional."""
    url = to_sync_database_url(settings.database_url).replace("postgresql+psycopg://", "postgresql://", 1)
    for attempt in range(5):
        try:
            with psycopg.connect(url, connect_timeout=20) as connection:
                connection.execute("set search_path = public, extensions")
                result = operation(connection)
            return result
        except (psycopg.OperationalError, psycopg.InterfaceError) as exc:
            sqlstate = getattr(exc, "sqlstate", None)
            transient = sqlstate is None or sqlstate.startswith("08") or sqlstate in {
                "40001", "40P01", "53300", "57P01", "57P02", "57P03",
            }
            if not transient or attempt == 4:
                raise
            delay = 2 ** (attempt + 1)
            logger.warning("Supabase connection interrupted; retrying in %ds (%d/4)", delay, attempt + 1)
            time.sleep(delay)
    raise RuntimeError("Unreachable database retry state")


def _vectors(settings: Settings, texts: list[str]) -> list[list[float]]:
    return embed_documents(settings, texts)


def ingest(settings: Settings, *, limit: int | None = None, direct_db: bool = False) -> tuple[int, int]:
    if direct_db and not settings.database_url:
        raise ConfigurationError("DATABASE_URL is required for --direct-db ingestion.")
    if not direct_db and not settings.is_cloud_rag_configured:
        raise ConfigurationError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.")
    try:
        from supabase import create_client
    except ImportError as exc:
        raise ConfigurationError("Install backend requirements before cloud ingestion.") from exc

    transcript_dir = Path(settings.transcripts_local_dir).expanduser()
    if not transcript_dir.is_absolute():
        transcript_dir = ROOT / transcript_dir
    transcript_dir = transcript_dir.resolve()
    if not transcript_dir.is_dir():
        raise ConfigurationError(f"Transcript directory does not exist: {transcript_dir}")
    client = None if direct_db else create_client(settings.supabase_url, settings.supabase_service_role_key)
    from tokenizers import Tokenizer

    # Clone BGE's tokenizer without changing the inference tokenizer. Counting
    # cl100k tokens or using 1,000-token chunks would truncate BGE's 512-token input.
    tokenizer = Tokenizer.from_str(embedding_model(settings).model.tokenizer.to_str())
    tokenizer.no_truncation()
    tokenizer.no_padding()
    splitter = RecursiveCharacterTextSplitter(
        length_function=lambda text: len(tokenizer.encode(text, add_special_tokens=False).ids),
        chunk_size=CHUNK_SIZE_TOKENS,
        chunk_overlap=CHUNK_OVERLAP_TOKENS, separators=["\n\n", "\n", ". ", " ", ""],
        add_start_index=True,
    )
    documents = chunks = 0
    pending: list[dict[str, object]] = []
    existing_ids: set[str] = set()
    if direct_db:
        from psycopg import sql

        def load_existing(connection: psycopg.Connection) -> set[str]:
            return {str(row[0]) for row in connection.execute(
                sql.SQL("select id from public.{}").format(sql.Identifier(settings.cloud_vector_table))
            ).fetchall()}
        existing_ids = _database_operation(settings, load_existing)
        logger.info("Resume: %d cloud chunks already stored", len(existing_ids))

    def flush() -> None:
        nonlocal chunks
        if not pending:
            return
        texts = [str(row["content"]) for row in pending]
        for row, vector in zip(pending, _vectors(settings, texts), strict=True):
            row["embedding"] = vector
        if direct_db:
            from psycopg import sql
            from psycopg.types.json import Jsonb

            def upsert_batch(connection: psycopg.Connection) -> None:
                with connection.cursor() as cursor:
                    cursor.executemany(sql.SQL("""
                        insert into public.{} (id, content, metadata, embedding)
                        values (%s, %s, %s, %s::vector)
                        on conflict (id) do update set content=excluded.content,
                          metadata=excluded.metadata, embedding=excluded.embedding, updated_at=now()
                    """).format(sql.Identifier(settings.cloud_vector_table)), [
                        (row["id"], row["content"], Jsonb(row["metadata"]), str(row["embedding"]))
                        for row in pending
                    ])
            _database_operation(settings, upsert_batch)
        else:
            assert client is not None
            client.table(settings.cloud_vector_table).upsert(pending, on_conflict="id").execute()
        chunks += len(pending)
        pending.clear()
        logger.info("Upserted %d cloud chunks", chunks)

    for document in _transcript_documents(transcript_dir):
        if Path(str(document.metadata["source_path"])).name.lower() in {"readme.md", "claude.md", "agents.md", "license.md"}:
            continue
        if limit is not None and documents >= limit:
            break
        documents += 1
        source = str(document.metadata["source_path"])
        for index, chunk in enumerate(splitter.split_documents([document])):
            chunk.metadata["source_path"] = source
            chunk.metadata["chunk_index"] = index
            chunk_id = _stable_chunk_id(chunk, index)
            if chunk_id in existing_ids:
                chunks += 1
                continue
            pending.append({
                "id": chunk_id,
                "content": chunk.page_content,
                "metadata": chunk.metadata,
            })
            if len(pending) >= BATCH_SIZE:
                flush()
        if documents % 100 == 0:
            logger.info("Processed %d transcripts; upserted %d chunks", documents, chunks)
    flush()
    return documents, chunks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=BACKEND / ".env.cloud")
    parser.add_argument("--limit", type=int, help="Ingest only this many files for a smoke test.")
    parser.add_argument("--direct-db", action="store_true", help="Use the existing Supabase DATABASE_URL instead of the REST API.")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        documents, chunks = ingest(Settings(_env_file=(BACKEND / ".env", args.env_file)), limit=args.limit, direct_db=args.direct_db)
    except ConfigurationError as exc:
        logger.error("Cloud ingestion failed: %s", exc)
        return 1
    except Exception as exc:
        logger.error("Cloud ingestion failed (%s); check model cache and Supabase connectivity.", type(exc).__name__)
        return 1
    logger.info("Cloud ingestion complete: %d transcripts, %d chunks", documents, chunks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
