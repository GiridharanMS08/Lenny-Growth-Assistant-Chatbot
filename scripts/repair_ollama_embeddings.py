"""Repair suspected overwritten vectors from exact stored chunks, with a backup."""
from __future__ import annotations

import argparse
import json
import logging
import math
from datetime import datetime, timezone

import psycopg

from migrate_gemini_embeddings import BACKEND, ROOT, Settings, _psycopg_url
from app.rag.embeddings import build_embeddings

logger = logging.getLogger(__name__)


def repair(apply: bool, all_rows: bool) -> None:
    settings = Settings(_env_file=BACKEND / ".env")
    url = _psycopg_url(settings.database_url)
    with psycopg.connect(url) as conn:
        rows = conn.execute("""SELECT e.id,e.collection_id,e.document,e.cmetadata,e.embedding::text
            FROM langchain_pg_embedding e JOIN langchain_pg_collection c ON c.uuid=e.collection_id
            WHERE c.name=%s AND (%s OR abs(vector_norm(e.embedding)-1)>0.0001)
            ORDER BY e.id""", (settings.vector_collection_name, all_rows)).fetchall()
    logger.info("Selected %d rows. Apply=%s", len(rows), apply)
    if not apply or not rows:
        return
    backup_dir = ROOT / "data" / "embedding-repair-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + ".jsonl")
    with backup.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(list(row), default=str, ensure_ascii=False) + "\n")
    logger.info("Original rows backed up to %s", backup)
    embeddings = build_embeddings(settings)
    for index, (row_id, collection_id, document, metadata, old_vector) in enumerate(rows, 1):
        if not isinstance(document, str):
            raise ValueError("Stored chunk is not text.")
        vector = embeddings.embed_documents([document])[0]
        if not vector or not all(math.isfinite(v) for v in vector):
            raise ValueError("Ollama returned an invalid vector.")
        if len(vector) != len(json.loads(old_vector)):
            raise ValueError("Ollama dimensions changed; refusing repair.")
        if abs(math.sqrt(sum(v*v for v in vector))-1) > 0.0001:
            raise ValueError("Ollama vector is not unit length; stop and inspect model.")
        with psycopg.connect(url) as conn:
            result = conn.execute("""UPDATE langchain_pg_embedding SET embedding=%s::vector
                WHERE id=%s AND collection_id=%s AND document=%s AND embedding=%s::vector
                RETURNING id""", (str(vector), row_id, collection_id, document, old_vector)).fetchone()
            if not result:
                raise ValueError("Source row changed concurrently; refusing to overwrite it.")
        logger.info("Repaired %d/%d vectors; text and metadata unchanged", index, len(rows))
    logger.info("Repair complete. Unit length is a damage heuristic, not proof of every other vector's origin.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Back up then repair; default is read-only inspection.")
    parser.add_argument("--all", action="store_true", help="Regenerate every local vector for complete provenance certainty.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    repair(args.apply, args.all)
