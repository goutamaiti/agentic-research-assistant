"""Paper-level schemas shared by processing, extraction and the API."""

from __future__ import annotations

from enum import StrEnum
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ExtractionStatus(StrEnum):
    """Specification §5.2 extraction status."""

    EXTRACTED = "extracted"
    NOT_FOUND = "not_found"
    PARTIALLY_EXTRACTED = "partially_extracted"
    AMBIGUOUS = "ambiguous"


MetadataSource = Literal["pdf_metadata", "first_page_layout", "text_pattern", "section_text"]


class MetadataField(BaseModel, Generic[T]):
    """One metadata value with explicit status and where it came from (spec §5.6)."""

    model_config = ConfigDict(extra="forbid")

    value: T | None = None
    status: ExtractionStatus = ExtractionStatus.NOT_FOUND
    source: MetadataSource | None = None
    pdf_page_index: int | None = None
    evidence_text: str | None = Field(default=None, description="Exact source text")
    note: str | None = None


class DocumentMetadata(BaseModel):
    """Deterministic metadata found during document processing.

    This is a preliminary record built without an LLM. The final ``paper_metadata`` of an
    analysis is produced by the extraction phase, which may resolve fields marked
    ``not_found`` here (for example author names), always with evidence.
    """

    model_config = ConfigDict(extra="forbid")

    method: Literal["deterministic"] = "deterministic"
    title: MetadataField[str] = Field(default_factory=MetadataField[str])
    authors: MetadataField[list[str]] = Field(default_factory=MetadataField[list[str]])
    publication_year: MetadataField[int] = Field(default_factory=MetadataField[int])
    journal_or_conference: MetadataField[str] = Field(default_factory=MetadataField[str])
    doi: MetadataField[str] = Field(default_factory=MetadataField[str])
    abstract: MetadataField[str] = Field(default_factory=MetadataField[str])
    keywords: MetadataField[list[str]] = Field(default_factory=MetadataField[list[str]])
    document_language: MetadataField[str] = Field(default_factory=MetadataField[str])
