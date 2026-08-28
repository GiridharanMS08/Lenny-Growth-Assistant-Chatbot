import pytest


def test_database_url_must_be_postgresql(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
    from app.config import Settings

    with pytest.raises(ValueError, match="PostgreSQL is required"):
        Settings(_env_file=None)


def test_database_url_can_be_loaded_from_environment(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:secret@localhost:5432/lenny",
    )
    from app.config import Settings

    settings = Settings(_env_file=None)
    assert settings.database_url.endswith("/lenny")
