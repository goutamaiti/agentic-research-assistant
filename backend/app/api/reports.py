"""Report export endpoints: generate (JSON or PDF) and download."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.analysis import get_analysis
from app.api.deps import get_session
from app.services import document_service
from app.services.report_service import ReportFormat, find_report, write_report

router = APIRouter(tags=["reports"])


class ReportRequest(BaseModel):
    format: ReportFormat = "pdf"


class ReportResponse(BaseModel):
    report_id: str
    format: ReportFormat
    download_url: str


@router.post("/documents/{document_id}/report", response_model=ReportResponse, status_code=201)
def create_report(
    document_id: str, body: ReportRequest, request: Request, session: Session = Depends(get_session)
) -> ReportResponse:
    analysis = get_analysis(document_id, session)  # 404 if there is no analysis yet
    document = document_service.get_document(session, document_id)
    report_id = write_report(
        request.app.state.settings, document_id, document.title, analysis.result, body.format
    )
    return ReportResponse(
        report_id=report_id, format=body.format, download_url=f"/api/reports/{report_id}"
    )


@router.get("/reports/{report_id}")
def download_report(report_id: str, request: Request) -> FileResponse:
    path = find_report(request.app.state.settings, report_id)
    media = "application/pdf" if path.suffix == ".pdf" else "application/json"
    return FileResponse(path, media_type=media, filename=f"research-analysis{path.suffix}")
