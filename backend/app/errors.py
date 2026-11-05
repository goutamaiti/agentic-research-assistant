"""Application errors that map to structured HTTP error responses."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """An expected failure with a stable machine-readable ``code``."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def document_not_found(document_id: str) -> AppError:
    return AppError(404, "document_not_found", f"Document {document_id} was not found.")
