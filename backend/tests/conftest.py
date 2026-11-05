"""Shared fixtures. Tests never read backend/.env and never call external APIs."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

# Every settings field, plus the SDK's alternative key variable.
_ENV_VARS = [name.upper() for name in Settings.model_fields] + ["GOOGLE_API_KEY"]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {"app_env": "test", "storage_dir": tmp_path / "storage"}
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
