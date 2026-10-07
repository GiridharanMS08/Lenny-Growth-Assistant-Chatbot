from __future__ import annotations

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.main import create_app


def test_health_check() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_models_reports_ollama_status(monkeypatch: MonkeyPatch) -> None:
    async def fake_list_models(*_: object) -> tuple[bool, list[str], str | None]:
        return True, ["llama3.2:3b", "nomic-embed-text"], None

    monkeypatch.setattr("app.api.routes.models.list_ollama_models", fake_list_models)
    with TestClient(create_app()) as client:
        response = client.get("/api/models")

    assert response.status_code == 200
    assert response.json()["local"]["available_models"] == ["llama3.2:3b", "nomic-embed-text"]
