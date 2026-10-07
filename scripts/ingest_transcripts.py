"""Incrementally ingest the public Lenny's Podcast transcript repository into Supabase."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import yaml
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import Settings  # noqa: E402
from app.core.errors import ConfigurationError  # noqa: E402
from app.rag.embeddings import build_embeddings, to_sync_database_url  # noqa: E402

logger = logging.getLogger("transcript_ingestion")
CHUNK_SIZE_TOKENS = 1_000
CHUNK_OVERLAP_TOKENS = 200
BATCH_SIZE = 32


def _sync_repository(repo_url: str, destination: Path) -> Path:
    """Clone once and fast-forward subsequent ingestions from the configured remote."""
    if (destination / ".git").is_dir():
        subprocess.run(
            ["git", "-C", str(destination), "pull", "--ff-only"],
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
    elif destination.exists() and any(destination.iterdir()):
        raise ConfigurationError(
            f"Transcript directory {destination} exists but is not a Git checkout. "
            "Move it or configure TRANSCRIPTS_LOCAL_DIR to an empty directory."
        )
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(destination)],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
    return destination


def _split_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    match = re.match(r"\A\ufeff?---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|\Z)", raw, re.DOTALL)
    if not match:
        return {}, raw
    parsed = yaml.safe_load(match.group(1))
    metadata = dict(parsed) if isinstance(parsed, Mapping) else {}
    return metadata, raw[match.end() :].strip()


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def _first(metadata: Mapping[str, Any], *names: str) -> str:
    lowered = {str(key).lower().replace("-", "_"): value for key, value in metadata.items()}
    for name in names:
        value = _as_text(lowered.get(name))
        if value:
            return value
    return ""


def _load_index_metadata(repo: Path) -> dict[str, dict[str, Any]]:
    """Read optional structured index files and map records by common slug/path keys."""
    index_dir = repo / "index"
    records: dict[str, dict[str, Any]] = {}
    if not index_dir.is_dir():
        return records
    for path in index_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".json", ".yaml", ".yml", ".md"}:
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            if path.suffix.lower() == ".json":
                data = json.loads(raw)
            elif path.suffix.lower() in {".yaml", ".yml"}:
                data = yaml.safe_load(raw)
            else:
                data, _ = _split_frontmatter(raw)
        except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
            logger.warning("Skipping unreadable index file %s: %s", path, exc)
            continue
        candidates = (
            data if isinstance(data, list) else data.values() if isinstance(data, dict) else []
        )
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            record = dict(candidate)
            keys = [_first(record, "slug", "id", "file", "filename", "path", "url")]
            keys.append(path.stem)
            for key in keys:
                if key:
                    normalized = Path(key.removesuffix(".md")).stem.lower()
                    records[normalized] = record
    return records


def _transcript_documents(repo: Path) -> Iterator[Document]:
    index = _load_index_metadata(repo)
    for path in sorted(repo.rglob("*.md")):
        if ".git" in path.parts or "index" in {
            part.lower() for part in path.relative_to(repo).parts[:-1]
        }:
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            logger.warning("Skipping unreadable transcript %s: %s", path, exc)
            continue
        frontmatter, body = _split_frontmatter(raw)
        index_metadata = index.get(path.stem.lower(), {})
        combined = {**dict(index_metadata), **frontmatter}
        title = _first(combined, "episode_title", "title", "episode", "name") or path.stem.replace(
            "-", " "
        ).replace("_", " ")
        guest = _first(combined, "guest_name", "guest", "author", "interviewee") or "Unknown guest"
        tags = _first(combined, "tags", "topics", "categories")
        source_path = path.relative_to(repo).as_posix()
        enriched = f"Episode Title: {title}\nGuest: {guest}\nTags: {tags or 'none'}\nSource: {source_path}\n\nTranscript:\n{body}".strip()
        if not body:
            logger.warning("Skipping empty transcript %s", source_path)
            continue
        yield Document(
            page_content=enriched,
            metadata={
                "episode_title": title,
                "guest_name": guest,
                "tags": tags,
                "source_path": source_path,
            },
        )


def _stable_chunk_id(doc: Document, chunk_index: int) -> str:
    fingerprint = hashlib.sha256(doc.page_content.encode("utf-8")).hexdigest()
    source = str(doc.metadata.get("source_path", "unknown"))
    return str(uuid5(NAMESPACE_URL, f"lenny-transcript:{source}:{chunk_index}:{fingerprint}"))


def ingest(settings: Settings) -> tuple[int, int]:
    if not settings.is_database_configured:
        raise ConfigurationError(
            "Set DATABASE_URL to your Supabase Cloud PostgreSQL connection string."
        )
    destination = Path(settings.transcripts_local_dir).expanduser().resolve()
    repo = _sync_repository(settings.transcripts_repo_url, destination)
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=CHUNK_SIZE_TOKENS,
        chunk_overlap=CHUNK_OVERLAP_TOKENS,
        separators=["\n\n", "\n", ". ", " ", ""],
        add_start_index=True,
    )
    try:
        from langchain_postgres import PGVector
    except ImportError as exc:
        raise ConfigurationError(
            "Install backend dependencies with `pip install -e backend`."
        ) from exc

    store = PGVector(
        embeddings=build_embeddings(settings),
        collection_name=settings.vector_collection_name,
        connection=to_sync_database_url(settings.database_url),
        # Embedding a batch can take several minutes. Validate pooled connections on
        # checkout so Supabase does not hand us a connection it closed while idle.
        engine_args={"pool_pre_ping": True},
        use_jsonb=True,
    )
    document_count = chunk_count = 0
    batch: list[Document] = []
    batch_ids: list[str] = []

    def flush() -> None:
        nonlocal chunk_count
        if batch:
            store.add_documents(batch, ids=batch_ids)
            chunk_count += len(batch)
            batch.clear()
            batch_ids.clear()

    for document in _transcript_documents(repo):
        document_count += 1
        source = str(document.metadata["source_path"])
        for index, chunk in enumerate(splitter.split_documents([document])):
            chunk.metadata["source_path"] = source
            chunk.metadata["chunk_index"] = index
            batch.append(chunk)
            batch_ids.append(_stable_chunk_id(chunk, index))
            if len(batch) >= BATCH_SIZE:
                flush()
        if document_count % 100 == 0:
            logger.info(
                "Prepared %d transcript files (%d chunks stored)", document_count, chunk_count
            )
    flush()
    return document_count, chunk_count


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        settings = Settings(_env_file=BACKEND / ".env")
        documents, chunks = ingest(settings)
    except Exception as exc:
        logger.error("Transcript ingestion failed: %s", exc)
        return 1
    logger.info("Ingestion complete: %d transcript files, %d chunks", documents, chunks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
