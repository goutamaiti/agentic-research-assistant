"""Analysis endpoints: start a run and report its status."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.api import AnalyzeResponse, StageStatus, StatusResponse
from app.services import document_service
from app.services.analysis_service import latest_run

router = APIRouter(prefix="/documents", tags=["analysis"])


@router.post("/{document_id}/analyze", response_model=AnalyzeResponse, status_code=202)
def start_analysis(
    document_id: str, request: Request, session: Session = Depends(get_session)
) -> AnalyzeResponse:
    """Queue processing and indexing; returns at once with the run id (poll ``/status``)."""
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
