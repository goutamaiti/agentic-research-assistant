"""Pydantic request/response models for the HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.database.models import (
    DocumentStatus,
    ExtractionRunStatus,
    PageExtractionStatus,
    RunStatus,
)
from app.schemas.extraction import ExtractionResult
from app.schemas.paper import DocumentMetadata

# "configured" means settings are present but the service was not contacted.
ComponentState = Literal["ok", "error", "configured", "not_configured"]


class ComponentHealth(BaseModel):
    status: ComponentState
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    app_name: str
    version: str
    environment: str
    components: dict[str, ComponentHealth] = Field(
        description="Per-component state: database, vector_store, llm, ocr, embeddings."
    )


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ----- Documents ----------------------------------------------------------------------


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    file_size: int
    sha256: str
    page_count: int | None
    title: str | None
    status: DocumentStatus
    status_detail: str | None
    created_at: datetime
    updated_at: datetime


class PageSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pdf_page_index: int
    displayed_page_number: str | None
    extraction_status: PageExtractionStatus
    ocr_used: bool
    char_count: int


class SectionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    section_index: int
    title: str
    level: int
    section_type: str
    parent_index: int | None
    start_page_index: int
    end_page_index: int


class IndexSummary(BaseModel):
    index_version: str | None
    embedding_model_id: str | None
    chunks_total: int
    chunks_indexed: int


class DocumentDetail(DocumentSummary):
    metadata: DocumentMetadata | None
    pages: list[PageSummary]
    sections: list[SectionSummary]
    index: IndexSummary


# ----- Analysis runs ------------------------------------------------------------------


class AnalyzeResponse(BaseModel):
    document_id: str
    workflow_run_id: str
    status: DocumentStatus


class StageStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage: str
    status: RunStatus
    started_at: datetime | None
    completed_at: datetime | None
    error: dict[str, Any] | None = Field(default=None, validation_alias="error_json")
    metrics: dict[str, Any] | None = Field(default=None, validation_alias="metrics_json")


class AnalysisResponse(BaseModel):
    """The latest validated structured analysis of a document."""

    document_id: str
    extraction_id: int
    status: ExtractionRunStatus
    created_at: datetime
    result: ExtractionResult


class StatusResponse(BaseModel):
    document_id: str
    status: DocumentStatus
    status_detail: str | None
    workflow_run_id: str | None
    stages: list[StageStatus]
