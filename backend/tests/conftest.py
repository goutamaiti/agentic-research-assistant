"""Shared fixtures. Tests never read backend/.env, never call external APIs, and never
download models: the embedding model, OCR engine and background runner are replaced by
fakes unless a test opts in to the real ones (``-m integration``)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.jobs import InlineJobRunner
from tests.fakes import FakeEmbedder, FakeOcr

# Every settings field, plus the SDK's alternative key variable.
_ENV_VARS = [name.upper() for name in Settings.model_fields] + ["GOOGLE_API_KEY"]


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("RUN_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(reason="integration test; set RUN_INTEGRATION=1 to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {"app_env": "test", "storage_dir": tmp_path / "storage"}
    values.update(overrides)
    return Settings(_env_file=None, **values)


def make_client(settings: Settings, **services: Any) -> TestClient:
    """A TestClient (use as a context manager) with fakes unless overridden."""
    services.setdefault("embedder", FakeEmbedder())
    services.setdefault("ocr_engine", FakeOcr(available=False))
    services.setdefault("job_runner", InlineJobRunner())
    return TestClient(create_app(settings, **services))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with make_client(settings) as test_client:
        yield test_client
