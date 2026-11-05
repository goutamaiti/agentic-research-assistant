"""Upload, registration and lookup of paper workspaces (one PDF per document)."""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.database.models import Document, DocumentStatus
from app.document_processing.pdf_parser import (
    HEADER_SEARCH_BYTES,
    PdfValidationError,
    has_pdf_header,
    validate_pdf,
)
from app.errors import AppError, document_not_found

logger = logging.getLogger(__name__)

_READ_SIZE = 1024 * 1024
_DOCUMENT_ID = re.compile(r"^[0-9a-f]{32}$")
_UNSAFE_FILENAME_CHARS = re.compile(r"[\x00-\x1f\x7f<>:\"/\\|?*]")

_VALIDATION_STATUS = {"not_pdf": 415, "encrypted_pdf": 422, "corrupt_pdf": 422, "empty_pdf": 422}


def safe_display_filename(name: str | None) -> str:
    """The user's filename, reduced to a harmless display string (never used on disk)."""
    base = Path((name or "").replace("\\", "/")).name
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", base).strip(" .")
    return (cleaned or "upload.pdf")[:255]


def resolve_document_file(settings: Settings, document: Document) -> Path:
    """Absolute path of a stored PDF, refusing anything outside the uploads directory."""
    uploads = settings.uploads_path.resolve()
    path = (settings.storage_path / document.file_path).resolve()
    if not path.is_relative_to(uploads):
        raise AppError(500, "invalid_storage_path", "Stored file path is outside the uploads area.")
    return path


def get_document(session: Session, document_id: str) -> Document:
    if not _DOCUMENT_ID.match(document_id):
        raise document_not_found(document_id)
    document = session.get(Document, document_id)
    if document is None:
        raise document_not_found(document_id)
    return document


def list_documents(session: Session) -> list[Document]:
    return list(session.scalars(select(Document).order_by(Document.created_at.desc())))


def _duplicate(existing: Document) -> AppError:
    return AppError(
        409,
        "duplicate_document",
        "This PDF has already been uploaded. Reuse the existing workspace, or delete it "
        "before uploading the file again.",
        details={"document_id": existing.id, "status": existing.status.value},
    )


def store_upload(
    session: Session, settings: Settings, stream: BinaryIO, original_filename: str | None
) -> Document:
    """Validate and store an uploaded PDF, returning its new document record.

    The size limit is enforced while reading. The content is checked as PDF regardless of
    the filename or declared content type.
    """
    settings.uploads_path.mkdir(parents=True, exist_ok=True)
    document_id = uuid.uuid4().hex
    stored_filename = f"{document_id}.pdf"
    temp_path = settings.uploads_path / f"{document_id}.part"
    final_path = settings.uploads_path / stored_filename
    digest = hashlib.sha256()
    size = 0
    committed = False

    try:
        with temp_path.open("wb") as out:
            first = True
            while chunk := stream.read(_READ_SIZE):
                if first:
                    if not has_pdf_header(chunk[:HEADER_SEARCH_BYTES]):
                        raise AppError(415, "not_pdf", "The file is not a PDF.")
                    first = False
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise AppError(
                        413,
                        "file_too_large",
                        f"The file exceeds the {settings.max_upload_mb} MB upload limit.",
                        details={"max_upload_mb": settings.max_upload_mb},
                    )
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise AppError(400, "empty_file", "The uploaded file is empty.")

        try:
            info = validate_pdf(temp_path)
        except PdfValidationError as exc:
            raise AppError(_VALIDATION_STATUS.get(exc.code, 422), exc.code, exc.message) from exc

        sha256 = digest.hexdigest()
        existing = session.scalar(select(Document).where(Document.sha256 == sha256))
        if existing is not None:
            raise _duplicate(existing)

        temp_path.replace(final_path)
        document = Document(
            id=document_id,
            original_filename=safe_display_filename(original_filename),
            stored_filename=stored_filename,
            file_path=final_path.relative_to(settings.storage_path).as_posix(),
            sha256=sha256,
            file_size=size,
            page_count=info.page_count,
            status=DocumentStatus.UPLOADED,
        )
        session.add(document)
        try:
            session.commit()
        except IntegrityError:
            # A concurrent upload of the same file won the race on the sha256 constraint.
            session.rollback()
            final_path.unlink(missing_ok=True)
            existing = session.scalar(select(Document).where(Document.sha256 == sha256))
            if existing is not None:
                raise _duplicate(existing) from None
            raise
        committed = True
        logger.info("Stored document %s (%d bytes, %d pages)", document_id, size, info.page_count)
        return document
    finally:
        temp_path.unlink(missing_ok=True)
        if not committed:
            # Never leave a stored PDF without its database record.
            final_path.unlink(missing_ok=True)
