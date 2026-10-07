"""Read original chunks; insert Gemini vectors into a separate physical table."""
import argparse
import logging
import sys
import time
from pathlib import Path

from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
from app.core.config import Settings  # noqa: E402
from app.rag.embeddings import build_gemini_embeddings, to_sync_database_url  # noqa: E402
from app.rag.gemini_store import connect, create_table  # noqa: E402

logger = logging.getLogger(__name__)


def _psycopg_url(url):
    return to_sync_database_url(url).replace("postgresql+psycopg://", "postgresql://", 1)


def migrate(settings, apply=False, delay=10):
    with connect(settings.database_url) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        rows = conn.execute("""SELECT e.id,e.document,e.cmetadata FROM langchain_pg_embedding e
            JOIN langchain_pg_collection c ON c.uuid=e.collection_id
            WHERE c.name=%s ORDER BY e.id""", (settings.vector_collection_name,)).fetchall()
    if not rows:
        raise ValueError("Source collection is empty.")
    logger.info("Source: %d chunks. Target: langchain_pg_embedding_gemini. Apply=%s", len(rows), apply)
    if not apply:
        return
    embeddings = build_gemini_embeddings(settings)
    scope = (settings.vector_collection_name, settings.gemini_embedding_model, settings.gemini_embedding_dimensions)
    with connect(settings.database_url) as conn:
        create_table(conn)
        saved = conn.execute("""SELECT source_id,document,cmetadata FROM public.langchain_pg_embedding_gemini
            WHERE source_collection=%s AND embedding_model=%s AND dimensions=%s""", scope).fetchall()
    existing = {r[0]: (r[1], r[2]) for r in saved}
    pending = []
    for source_id, document, metadata in rows:
        if not isinstance(document, str):
            raise ValueError("Invalid source text; refusing conversion.")
        if source_id in existing:
            if existing[source_id] != (document, metadata):
                raise ValueError("Saved chunk differs; refusing overwrite.")
        else:
            pending.append((source_id, document, metadata))
    done = len(rows)-len(pending)
    logger.info("Already saved %d; remaining %d", done, len(pending))
    size = settings.gemini_embedding_batch_size
    for start in range(0, len(pending), size):
        batch = pending[start:start+size]
        vectors = embeddings.embed_documents([r[1] for r in batch])
        with connect(settings.database_url) as conn:
            for (source_id, document, metadata), vector in zip(batch, vectors, strict=True):
                conn.execute("""INSERT INTO public.langchain_pg_embedding_gemini
                    (source_id,source_collection,embedding_model,dimensions,document,cmetadata,embedding)
                    VALUES(%s,%s,%s,%s,%s,%s,%s::vector)""",
                    (source_id, *scope, document, Jsonb(metadata), str(vector)))
        done += len(batch)
        logger.info("Saved %d/%d Gemini vectors in NEW table", done, len(rows))
        if start+size < len(pending):
            time.sleep(delay)
    logger.info("Complete. Original tables unchanged; no rechunking.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--delay", type=float, default=10)
    args = parser.parse_args()
    if args.delay < 0:
        parser.error("Delay must be nonnegative")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    migrate(Settings(_env_file=BACKEND / ".env"), args.apply, args.delay)
