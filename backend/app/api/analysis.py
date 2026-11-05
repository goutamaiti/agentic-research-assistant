"""Analysis endpoints: start a run, report its status, return the structured analysis."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.database.models import Extraction
from app.errors import AppError
from app.schemas.api import AnalysisResponse, AnalyzeResponse, StageStatus, StatusResponse
from app.schemas.extraction import ExtractionResult
from app.services import document_service
from app.services.analysis_service import latest_run

router = APIRouter(prefix="/documents", tags=["analysis"])


@router.post("/{document_id}/analyze", response_model=AnalyzeResponse, status_code=202)
def start_analysis(
    document_id: str, request: Request, session: Session = Depends(get_session)
) -> AnalyzeResponse:
    """Queue processing, indexing and extraction; returns at once (poll ``/status``)."""
    run_id = request.app.state.analysis_service.start(document_id)
    document = document_service.get_document(session, document_id)
    session.refresh(document)
    return AnalyzeResponse(document_id=document_id, workflow_run_id=run_id, status=document.status)


@router.get("/{document_id}/status", response_model=StatusResponse)
def analysis_status(document_id: str, session: Session = Depends(get_session)) -> StatusResponse:
    document = document_service.get_document(session, document_id)
    run_id, stages = latest_run(session, document_id)
    return StatusResponse(
        document_id=document_id,
        status=document.status,
        status_detail=document.status_detail,
        workflow_run_id=run_id,
        stages=[StageStatus.model_validate(stage) for stage in stages],
    )


@router.get("/{document_id}/analysis", response_model=AnalysisResponse)
def get_analysis(document_id: str, session: Session = Depends(get_session)) -> AnalysisResponse:
    """The latest structured analysis, validated against the extraction schema."""
    document = document_service.get_document(session, document_id)
    extraction = session.scalar(
        select(Extraction)
        .where(Extraction.document_id == document_id)
        .order_by(Extraction.id.desc())
        .limit(1)
    )
    if extraction is None:
        raise AppError(
            404,
            "analysis_not_found",
            "No analysis exists for this document yet. Run the analysis; knowledge "
            "extraction needs a configured Gemini API key.",
            details={"status": document.status.value},
        )
    return AnalysisResponse(
        document_id=document_id,
        extraction_id=extraction.id,
        status=extraction.status,
        created_at=extraction.created_at,
        result=ExtractionResult.model_validate(extraction.result_json),
    )
