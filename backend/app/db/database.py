from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings
from app.logging_config import db_logger

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    db_logger.info("session opened")
    try:
        yield db
    finally:
        db.close()
        db_logger.info("session closed")


def check_database_connection() -> None:
    """Raise a clear error when PostgreSQL is unreachable."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        db_logger.info("connectivity check ok")
    except Exception as exc:
        db_logger.error("connectivity check failed error_type=%s", type(exc).__name__)
        raise
