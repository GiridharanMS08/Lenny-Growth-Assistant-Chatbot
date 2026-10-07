"""Install the isolated cloud schema and ensure chat tables exist.

Requires --apply to write; otherwise only inspects the existing schema.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import Settings  # noqa: E402
from app.core.errors import ConfigurationError  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.rag.embeddings import to_sync_database_url  # noqa: E402


def initialize(settings: Settings, *, apply: bool = False) -> None:
    if not settings.database_url:
        raise ConfigurationError("DATABASE_URL is required for Supabase schema setup.")
    url = to_sync_database_url(settings.database_url)
    with psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://", 1), connect_timeout=20) as conn:
        conn.execute("set search_path = public, extensions")
        existing = conn.execute("select to_regclass('public.transcript_chunks_cloud')").fetchone()[0]
        if existing:
            columns = dict(conn.execute("""
                select attname, format_type(atttypid, atttypmod)
                from pg_attribute where attrelid = 'public.transcript_chunks_cloud'::regclass
                and attnum > 0 and not attisdropped
            """).fetchall())
            if any(columns.get(name) != expected for name, expected in {
                "id": "uuid", "content": "text", "metadata": "jsonb", "embedding": "vector(384)"
            }.items()):
                raise ConfigurationError("Existing cloud table has an incompatible schema; refusing to modify it.")
        function = conn.execute("""
            select p.oid, pg_get_functiondef(p.oid)
            from pg_proc p join pg_namespace n on n.oid=p.pronamespace
            where n.nspname='public' and p.proname='match_transcript_chunks'
        """).fetchall()
        if any("public.transcript_chunks_cloud" not in definition for _, definition in function):
            raise ConfigurationError("match_transcript_chunks already serves another table; refusing to overwrite it.")
        print(f"Cloud table exists: {bool(existing)}. Cloud RPC exists: {bool(function)}.")
        if apply:
            conn.execute((ROOT / "supabase" / "cloud_rag.sql").read_text(encoding="utf-8"))
            print("Applied the isolated cloud pgvector schema and service-role permissions.")
    if apply:
        engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 20})
        try:
            with engine.begin() as conn:
                Base.metadata.create_all(conn, tables=[Base.metadata.tables[name] for name in ("sessions", "messages")])
            print("Ensured sessions and messages tables exist.")
        finally:
            engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--env-file", type=Path, default=BACKEND / ".env.cloud")
    args = parser.parse_args()
    try:
        initialize(Settings(_env_file=(BACKEND / ".env", args.env_file)), apply=args.apply)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        # Drivers may include the DSN/password in connection errors.
        print(f"Supabase schema setup failed ({type(exc).__name__}); check database connectivity.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
