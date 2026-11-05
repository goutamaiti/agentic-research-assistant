from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import PROJECT_ROOT, Settings
from tests.conftest import make_settings


def test_defaults_match_specification(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    assert settings.gemini_model == "gemini-3.8-flash"
    assert settings.embedding_model == "sentence-transformers/multi-qa-mpnet-base-cos-v1"
    assert settings.max_upload_mb == 30
    assert settings.max_verification_retries == 2
    assert settings.anonymized_telemetry is False
    assert settings.llm_configured is False


def test_relative_storage_resolves_against_project_root() -> None:
    settings = Settings(_env_file=None, storage_dir=Path("storage"))
    assert settings.storage_path == (PROJECT_ROOT / "storage").resolve()
    assert settings.chroma_path == settings.storage_path / "chroma"
    assert settings.sqlalchemy_url.startswith("sqlite:///")
    assert settings.sqlalchemy_url.endswith("storage/database/app.db")


def test_relative_sqlite_database_url_resolves_against_project_root(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, database_url="sqlite:///storage/database/custom.db")
    expected = (PROJECT_ROOT / "storage" / "database" / "custom.db").resolve()
    assert settings.sqlite_file == expected
    assert settings.sqlalchemy_url == f"sqlite:///{expected.as_posix()}"


def test_absolute_and_non_file_database_urls(tmp_path: Path) -> None:
    absolute = (tmp_path / "abs.db").resolve()
    settings = make_settings(tmp_path, database_url=f"sqlite:///{absolute.as_posix()}")
    assert settings.sqlite_file == absolute
    settings.ensure_storage_dirs()
    memory = make_settings(tmp_path, database_url="sqlite:///:memory:")
    assert memory.sqlite_file is None
    assert memory.sqlalchemy_url == "sqlite:///:memory:"


def test_environment_variables_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.6-flash")
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    settings = Settings(_env_file=None, storage_dir=tmp_path)
    assert settings.gemini_model == "gemini-3.6-flash"
    assert settings.cors_origins == ["http://a.test", "http://b.test"]
    assert settings.log_level == "DEBUG"


def test_api_key_is_secret_and_blank_means_unset(tmp_path: Path) -> None:
    secret = "test-key-not-real-123"
    settings = make_settings(tmp_path, gemini_api_key=secret)
    assert settings.llm_configured is True
    assert secret not in repr(settings)
    assert secret not in str(settings.model_dump())
    assert make_settings(tmp_path, gemini_api_key="   ").llm_configured is False


def test_invalid_values_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        make_settings(tmp_path, max_upload_mb=0)
    with pytest.raises(ValidationError):
        make_settings(tmp_path, log_level="LOUD")


def test_ensure_storage_dirs_creates_layout(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    settings.ensure_storage_dirs()
    for sub in ("uploads", "reports", "chroma", "database"):
        assert (settings.storage_path / sub).is_dir()
