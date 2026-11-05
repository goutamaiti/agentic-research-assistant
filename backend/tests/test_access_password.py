"""Optional shared password for public deployments (ACCESS_PASSWORD)."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import make_client, make_settings


def test_no_password_configured_leaves_api_open(tmp_path: Path) -> None:
    with make_client(make_settings(tmp_path)) as client:
        assert client.get("/api/documents").status_code == 200


def test_password_required_on_api_but_not_on_health(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, access_password="open sesame")
    with make_client(settings) as client:
        assert client.get("/api/health").status_code == 200
        denied = client.get("/api/documents")
        assert denied.status_code == 401
        assert denied.json()["error"]["code"] == "access_denied"
        wrong = client.get("/api/documents", headers={"X-Access-Password": "nope"})
        assert wrong.status_code == 401
        ok = client.get("/api/documents", headers={"X-Access-Password": "open sesame"})
        assert ok.status_code == 200
        # Report downloads use random IDs; an unknown one is a 404, not a password prompt.
        assert client.get("/api/reports/" + "0" * 32).status_code == 404
        # Uploads are protected too.
        pdf = {"file": ("a.pdf", b"%PDF-1.4", "application/pdf")}
        upload = client.post("/api/documents/upload", files=pdf)
        assert upload.status_code == 401


def test_blank_password_means_disabled(tmp_path: Path) -> None:
    with make_client(make_settings(tmp_path, access_password="  ")) as client:
        assert client.get("/api/documents").status_code == 200
