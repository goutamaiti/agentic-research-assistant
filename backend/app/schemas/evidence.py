"""Claims and evidence records (specification §4.2D, §5.2, §5.4, §5.5).

Every factual statement in an analysis is a *claim* with a stable ID. Claims point to
*evidence records* by ID; an evidence record holds the exact source text and where it is
in the PDF. Extraction status and verification status are separate fields.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.paper import ExtractionStatus

CLAIM_ID_PATTERN = r"^CLM_\d{3,}$"
EVIDENCE_ID_PATTERN = r"^EVD_\d{3,}$"


class VerificationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    NOT_VERIFIABLE = "not_verifiable"


class Origin(StrEnum):
    AUTHOR_CLAIMED = "author_claimed"  # stated or clearly claimed by the authors
    SYSTEM_INFERRED = "system_inferred"  # cautious interpretation by the system
    DIRECTLY_EXTRACTED = "directly_extracted"  # factual content taken from the paper
    SYSTEM_EXPLANATION = "system_explanation"  # explanatory text written by the system


class QuoteMatch(StrEnum):
    """How the quoted source text was found in the stored document text."""

    EXACT = "exact"  # verbatim in the cited passage
    NORMALIZED = "normalized"  # same text after whitespace/quote/dash/case normalisation
    NOT_FOUND = "not_found"  # not in any supplied passage: no page reference is given
    PDF_METADATA = "pdf_metadata"  # from the PDF's embedded metadata, not visible on a page


ClaimCategory = Literal[
    "paper_metadata",
    "abstract",
    "research_problem",
    "objective",
    "motivation",
    "background",
    "methodology",
    "algorithm",
    "dataset",
    "experimental_setup",
    "result",
    "limitation",
    "future_scope",
    "methodology_step",
    "contribution",
    "terminology",
]


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(pattern=EVIDENCE_ID_PATTERN)
    claim_id: str = Field(pattern=CLAIM_ID_PATTERN)
    chunk_id: str | None = None
    pdf_page_index: int | None = Field(default=None, ge=0, description="Zero-based PDF page")
    displayed_page_number: str | None = Field(default=None, description="Printed page label")
    section_name: str | None = None
    source_text: str
    quote_match: QuoteMatch
    verification_status: VerificationStatus = VerificationStatus.PENDING
    verification_explanation: str | None = None


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(pattern=CLAIM_ID_PATTERN)
    category: ClaimCategory
    claim_text: str
    origin: Origin
    extraction_status: ExtractionStatus = ExtractionStatus.EXTRACTED
    verification_status: VerificationStatus = VerificationStatus.PENDING
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional; not a calibrated probability. Verification is separate.",
    )
    evidence_ids: list[str] = Field(default_factory=list)
    verification_explanation: str | None = None
    field_path: str = Field(
        description="Location of the claim in the analysis, e.g. "
        "'research_analysis.objectives.items[0]'"
    )
