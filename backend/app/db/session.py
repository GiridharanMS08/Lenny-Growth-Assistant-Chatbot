from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.errors import ConfigurationError
from app.db.models import Base


@lru_cache(maxsize=1)
def create_engine_from_settings() -> AsyncEngine:
    settings = get_settings()
    if not settings.is_database_configured:
        raise ConfigurationError(
            "DATABASE_URL is not configured. Set it to your Supabase Cloud asyncpg URL."
        )
    if not settings.database_url.startswith("postgresql+asyncpg://"):
        raise ConfigurationError(
            "DATABASE_URL must start with postgresql+asyncpg:// for the FastAPI database engine."
        )

    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=create_engine_from_settings(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_db_session() -> AsyncIterator[AsyncSession]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session


async def create_db_tables() -> None:
    """Create Phase 1 tables when explicitly enabled for quick setup."""
    engine = create_engine_from_settings()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
