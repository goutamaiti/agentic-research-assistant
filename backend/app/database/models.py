"""ORM models for documents, their pages/sections/chunks, and processing runs.

Status columns are stored as strings with CHECK constraints generated from Python enums,
so arbitrary status values are rejected by the database as well as by the application.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.database.connection import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC timestamps.

    SQLite stores no offset, so values would come back naive and be serialised without a
    timezone. Values are normalised to UTC on write and marked as UTC on read.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime; use timezone-aware UTC values")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
        length=32,
    )


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    INDEXED = "indexed"
    PARTIALLY_INDEXED = "partially_indexed"  # indexed, but some pages could not be read
    FAILED = "failed"


class PageExtractionStatus(StrEnum):
    EXTRACTED = "extracted"  # text layer used
    OCR_EXTRACTED = "ocr_extracted"  # OCR text used
    OCR_FAILED = "ocr_failed"  # scanned page, OCR ran but produced no usable text
    OCR_UNAVAILABLE = "ocr_unavailable"  # scanned page, OCR engine not installed
    EMPTY = "empty"  # no text layer and OCR found nothing (e.g. blank page)


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"  # stage finished with warnings that limit the result
    FAILED = "failed"
    SKIPPED = "skipped"
    INTERRUPTED = "interrupted"  # process stopped while the stage was running


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(64), unique=True)
    # Relative to the storage directory, so no machine-specific absolute path is stored.
    file_path: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    file_size: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int | None] = mapped_column(Integer)

    title: Mapped[str | None] = mapped_column(Text)
    authors_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    publication_year: Mapped[int | None] = mapped_column(Integer)
    doi: Mapped[str | None] = mapped_column(String(255))
    # Full deterministic metadata record, including per-field status and evidence.
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    status: Mapped[DocumentStatus] = mapped_column(
        _enum(DocumentStatus, "document_status"), default=DocumentStatus.UPLOADED
    )
    status_detail: Mapped[str | None] = mapped_column(Text)
    index_version: Mapped[str | None] = mapped_column(String(32))
    embedding_model_id: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    pages: Mapped[list[DocumentPage]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentPage.pdf_page_index",
    )
    sections: Mapped[list[DocumentSection]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentSection.section_index",
    )
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentChunk.chunk_index",
    )
    runs: Mapped[list[ProcessingRun]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProcessingRun.id",
    )


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "pdf_page_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    pdf_page_index: Mapped[int] = mapped_column(Integer)  # zero-based physical page
    displayed_page_number: Mapped[str | None] = mapped_column(String(32))  # printed label
    page_text: Mapped[str] = mapped_column(Text, default="")
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    extraction_status: Mapped[PageExtractionStatus] = mapped_column(
        _enum(PageExtractionStatus, "page_extraction_status")
    )
    char_count: Mapped[int] = mapped_column(Integer, default=0)

    document: Mapped[Document] = relationship(back_populates="pages")


class DocumentSection(Base):
    __tablename__ = "document_sections"
    __table_args__ = (UniqueConstraint("document_id", "section_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    section_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    level: Mapped[int] = mapped_column(Integer)  # 1 = top level
    section_type: Mapped[str] = mapped_column(String(32))  # canonical type, e.g. "methodology"
    parent_index: Mapped[int | None] = mapped_column(Integer)
    start_page_index: Mapped[int] = mapped_column(Integer)
    end_page_index: Mapped[int] = mapped_column(Integer)

    document: Mapped[Document] = relationship(back_populates="sections")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[str] = mapped_column(String(64), unique=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    section_index: Mapped[int | None] = mapped_column(Integer)
    section_name: Mapped[str | None] = mapped_column(Text)
    section_type: Mapped[str | None] = mapped_column(String(32))
    pdf_page_start: Mapped[int] = mapped_column(Integer)
    pdf_page_end: Mapped[int] = mapped_column(Integer)
    displayed_page_start: Mapped[str | None] = mapped_column(String(32))
    displayed_page_end: Mapped[str | None] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    indexed: Mapped[bool] = mapped_column(Boolean, default=True)  # False: kept, not embedded
    index_version: Mapped[str] = mapped_column(String(32))

    document: Mapped[Document] = relationship(back_populates="chunks")


class ProcessingRun(Base):
    """One row per workflow stage; rows of one run share ``workflow_run_id``."""

    __tablename__ = "processing_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    workflow_run_id: Mapped[str] = mapped_column(String(32), index=True)
    stage: Mapped[str] = mapped_column(String(64))
    status: Mapped[RunStatus] = mapped_column(_enum(RunStatus, "run_status"))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    document: Mapped[Document] = relationship(back_populates="runs")
