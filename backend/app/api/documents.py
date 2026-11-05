"""Document workspace endpoints: upload, list, details."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.database.models import DocumentChunk
from app.schemas.api import (
    DocumentDetail,
    DocumentSummary,
    IndexSummary,
    PageSummary,
    SectionSummary,
)
from app.schemas.paper import DocumentMetadata
from app.services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentSummary, status_code=201)
def upload_document(
    request: Request,
    file: UploadFile = File(..., description="One academic paper as a PDF"),
    session: Session = Depends(get_session),
) -> DocumentSummary:
    document = document_service.store_upload(
        session, request.app.state.settings, file.file, file.filename
    )
    return DocumentSummary.model_validate(document)


@router.get("", response_model=list[DocumentSummary])
def list_documents(session: Session = Depends(get_session)) -> list[DocumentSummary]:
    return [DocumentSummary.model_validate(d) for d in document_service.list_documents(session)]


@router.get("/{document_id}", response_model=DocumentDetail)
def document_detail(document_id: str, session: Session = Depends(get_session)) -> DocumentDetail:
    document = document_service.get_document(session, document_id)
    total, indexed = session.execute(
        select(
            func.count(), func.coalesce(func.sum(case((DocumentChunk.indexed, 1), else_=0)), 0)
        ).where(DocumentChunk.document_id == document_id)
    ).one()
    summary = DocumentSummary.model_validate(document)
    return DocumentDetail(
        **summary.model_dump(),
        metadata=(
            DocumentMetadata.model_validate(document.metadata_json)
            if document.metadata_json
            else None
        ),
        pages=[PageSummary.model_validate(p) for p in document.pages],
        sections=[SectionSummary.model_validate(s) for s in document.sections],
        index=IndexSummary(
            index_version=document.index_version,
            embedding_model_id=document.embedding_model_id,
            chunks_total=total,
            chunks_indexed=int(indexed),
        ),
    )
