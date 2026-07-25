import os

from fastapi.testclient import TestClient

from gitrag.api.app import create_app
from gitrag.config import get_settings
from gitrag.db.session import create_all


def test_health_and_ready_with_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("GITRAG_VECTOR_BACKEND", "memory")
    monkeypatch.setenv("GITRAG_DETERMINISTIC_EMBEDDINGS", "true")

    import gitrag.db.session as session_module

    session_module._engine = None
    session_module._SessionLocal = None
    create_all()

    app = create_app(get_settings())
    client = TestClient(app)

    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/readyz").json()["status"] == "ready"


def test_webhook_rejects_bad_signature(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "secret")

    import gitrag.db.session as session_module

    session_module._engine = None
    session_module._SessionLocal = None
    create_all()

    app = create_app(get_settings())
    client = TestClient(app)

    response = client.post(
        "/webhooks/github",
        content=b"{}",
        headers={"x-hub-signature-256": "sha256=bad", "x-github-delivery": "d1"},
    )

    assert response.status_code == 401
