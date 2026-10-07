"""Create the chat tables without modifying the LangChain vector tables."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db.models import Base  # noqa: E402
from app.db.session import create_engine_from_settings  # noqa: E402

CHAT_TABLES = [Base.metadata.tables[name] for name in ("sessions", "messages")]


async def main() -> None:
    engine = create_engine_from_settings()
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    tables=CHAT_TABLES,
                )
            )
        print("Ensured sessions and messages tables exist.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
