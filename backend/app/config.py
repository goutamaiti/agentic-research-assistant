"""Centralized application settings.

All configuration is read from environment variables (optionally via ``backend/.env``).
Relative storage paths are resolved against the project root, so no machine-specific
absolute path is ever hardcoded.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlencode

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent

APP_NAME = "Agentic Research Assistant"
APP_VERSION = "0.2.0"

# Bump when chunking or indexing behaviour changes, so stored indexes can be identified.
INDEX_VERSION = "1"


class Settings(BaseSettings):
    """Typed settings. Secrets use ``SecretStr`` so they never appear in reprs or logs."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    storage_dir: Path = Path("storage")
    database_url: str | None = None
    chroma_dir: Path | None = None

    max_upload_mb: int = Field(default=30, gt=0)

    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    llm_max_retries: int = Field(default=3, ge=0)

    embedding_model: str = "sentence-transformers/multi-qa-mpnet-base-cos-v1"
    embedding_device: str = "cpu"
    embedding_batch_size: int = Field(default=16, gt=0)

    # --- Document processing (starting values from the specification; tune by evaluation)
    tesseract_cmd: str | None = None  # path to tesseract executable if not on PATH
    ocr_language: str = "eng"
    ocr_dpi: int = Field(default=300, ge=72)
    ocr_min_text_chars: int = Field(default=40, ge=0)  # below this a page counts as scanned
    chunk_target_tokens: int = Field(default=220, gt=0)
    chunk_overlap_tokens: int = Field(default=40, ge=0)
    # Hard cap per chunk. The embedding model truncates at 512 word pieces and was trained
    # on inputs up to 250, so chunks stay near that length.
    chunk_max_tokens: int = Field(default=256, gt=0)
    index_references: bool = False

    # --- Retrieval
    semantic_candidates: int = Field(default=8, gt=0)
    bm25_candidates: int = Field(default=8, gt=0)

    max_verification_retries: int = Field(default=2, ge=0)

    anonymized_telemetry: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("gemini_api_key", mode="before")
    @classmethod
    def _blank_key_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    # ----- Derived paths -------------------------------------------------------------

    @staticmethod
    def _resolve(path: Path) -> Path:
        return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()

    @model_validator(mode="after")
    def _check_chunk_sizes(self) -> Settings:
        if self.chunk_overlap_tokens >= self.chunk_target_tokens:
            raise ValueError("chunk_overlap_tokens must be smaller than chunk_target_tokens")
        if self.chunk_max_tokens < self.chunk_target_tokens:
            raise ValueError("chunk_max_tokens must be at least chunk_target_tokens")
        return self

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def storage_path(self) -> Path:
        return self._resolve(self.storage_dir)

    @property
    def uploads_path(self) -> Path:
        return self.storage_path / "uploads"

    @property
    def reports_path(self) -> Path:
        return self.storage_path / "reports"

    @property
    def chroma_path(self) -> Path:
        return self._resolve(self.chroma_dir) if self.chroma_dir else self.storage_path / "chroma"

    @property
    def sqlite_file(self) -> Path | None:
        """Absolute path of the SQLite database file, or None for non-file databases."""
        if not self.database_url:
            return self.storage_path / "database" / "app.db"
        url = make_url(self.database_url)
        if url.get_backend_name() != "sqlite" or url.database in (None, "", ":memory:"):
            return None
        return self._resolve(Path(url.database))

    @property
    def sqlalchemy_url(self) -> str:
        """Database URL; relative SQLite paths are resolved against the project root."""
        sqlite_file = self.sqlite_file
        if sqlite_file is None:
            return self.database_url or ""
        # Built by hand: URL.render_as_string() percent-encodes the Windows drive colon.
        url = make_url(self.database_url) if self.database_url else None
        driver = url.drivername if url else "sqlite"
        query = f"?{urlencode(url.query, doseq=True)}" if url and url.query else ""
        return f"{driver}:///{sqlite_file.as_posix()}{query}"

    @property
    def llm_configured(self) -> bool:
        return self.gemini_api_key is not None

    def ensure_storage_dirs(self) -> None:
        """Create the controlled storage directories if they do not exist."""
        paths = [self.uploads_path, self.reports_path, self.chroma_path]
        if self.sqlite_file is not None:
            paths.append(self.sqlite_file.parent)
        for path in paths:
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance (overridable in tests)."""
    return Settings()
