from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.database.connection import create_db_engine
from app.main import create_app
from tests.conftest import make_settings


def test_health_ok(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"
    assert body["components"]["database"]["status"] == "ok"
    assert body["components"]["vector_store"]["status"] == "ok"
    assert body["components"]["llm"]["status"] == "not_configured"
    assert body["components"]["llm"]["detail"] == "model=gemini-3.8-flash"


def test_health_reports_llm_configured_without_leaking_key(tmp_path: Path) -> None:
    secret = "test-key-not-real-456"
    settings = make_settings(tmp_path, gemini_api_key=secret)
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health")
    assert response.json()["components"]["llm"]["status"] == "configured"
    assert secret not in response.text


def test_health_degraded_when_database_unreachable(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        # A directory cannot be opened as an SQLite database file.
        broken_dir = tmp_path / "not_a_db_file"
        broken_dir.mkdir()
        client.app.state.db_engine = create_db_engine(f"sqlite:///{broken_dir.as_posix()}")
        response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["components"]["database"]["status"] == "error"
    assert body["components"]["vector_store"]["status"] == "ok"


def test_unknown_route_returns_structured_error(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "http_404", "message": "Not Found"}}


def test_method_not_allowed_keeps_allow_header(client: TestClient) -> None:
    response = client.post("/api/health")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "http_405"
    assert "GET" in response.headers["allow"]


def test_validation_error_does_not_echo_input(settings) -> None:
    app = create_app(settings)

    @app.post("/api/_probe")
    def probe(payload: dict[str, int]) -> dict[str, int]:
        return payload

    with TestClient(app) as client:
        response = client.post("/api/_probe", json={"n": "PRIVATE-VALUE-123"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "body.n" in body["error"]["message"]
    assert "PRIVATE-VALUE-123" not in response.text


def test_importing_main_has_no_side_effects(monkeypatch) -> None:
    import importlib

    import app.main

    # An invalid setting must not break a plain import; settings load only in create_app().
    monkeypatch.setenv("LOG_LEVEL", "LOUD")
    importlib.reload(app.main)
    assert not hasattr(app.main, "app")


def test_startup_creates_storage_layout(client: TestClient) -> None:
    settings = client.app.state.settings
    for sub in ("uploads", "reports", "chroma", "database"):
        assert (settings.storage_path / sub).is_dir()


def test_cors_allows_configured_origin_only(client: TestClient) -> None:
    allowed = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    blocked = client.get("/api/health", headers={"Origin": "http://evil.test"})
    assert "access-control-allow-origin" not in blocked.headers
