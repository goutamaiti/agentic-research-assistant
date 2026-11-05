"""Search over one indexed document: semantic (Chroma) and keyword (BM25).

Phase 2 exposes the two retrievers separately so indexing can be checked. Rank fusion
(RRF), section filters and the Q&A workflow are added in Phase 6 (``hybrid_search``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from chromadb.api import ClientAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import DocumentChunk, DocumentStatus
from app.errors import AppError
from app.retrieval.embeddings import Embedder
from app.retrieval.keyword_search import KeywordIndex
from app.retrieval.vector_store import semantic_search
from app.services.document_service import get_document

SEARCHABLE_STATUSES = (
    DocumentStatus.INDEXED,
    DocumentStatus.PARTIALLY_INDEXED,
    DocumentStatus.ANALYZED,
    DocumentStatus.PARTIALLY_ANALYZED,
)


@dataclass(slots=True)
class SearchHit:
    chunk_id: str
    rank: int
    score: float
    retriever: Literal["semantic", "keyword"]
    text: str
    pdf_page_start: int
    pdf_page_end: int
    displayed_page_start: str | None
    section_name: str | None
    section_type: str | None


def _indexed_chunks(session: Session, document_id: str) -> list[DocumentChunk]:
    document = get_document(session, document_id)
    if document.status not in SEARCHABLE_STATUSES:
        raise AppError(
            409,
            "document_not_indexed",
            "This document has not been indexed yet. Run the analysis first.",
            details={"status": document.status.value},
        )
    return list(
        session.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id, DocumentChunk.indexed.is_(True))
            .order_by(DocumentChunk.chunk_index)
        )
    )


def _hit(chunk: DocumentChunk, rank: int, score: float, retriever) -> SearchHit:
    return SearchHit(
        chunk_id=chunk.chunk_id,
        rank=rank,
        score=score,
        retriever=retriever,
        text=chunk.text,
        pdf_page_start=chunk.pdf_page_start,
        pdf_page_end=chunk.pdf_page_end,
        displayed_page_start=chunk.displayed_page_start,
        section_name=chunk.section_name,
        section_type=chunk.section_type,
    )


def search_semantic(
    session: Session, client: ClientAPI, embedder: Embedder, document_id: str, query: str, k: int
) -> list[SearchHit]:
    chunks = {c.chunk_id: c for c in _indexed_chunks(session, document_id)}
    hits = semantic_search(client, document_id, embedder.embed_query(query), k)
    # Results are mapped back to SQLite rows; a vector without a row is never returned.
    return [
        _hit(chunks[h.chunk_id], rank, 1.0 - h.distance, "semantic")
        for rank, h in enumerate((h for h in hits if h.chunk_id in chunks), start=1)
    ]


def search_keyword(session: Session, document_id: str, query: str, k: int) -> list[SearchHit]:
    chunks = _indexed_chunks(session, document_id)
    index = KeywordIndex(
        [c.chunk_id for c in chunks], [f"{c.section_name or ''}\n{c.text}" for c in chunks]
    )
    by_id = {c.chunk_id: c for c in chunks}
    return [
        _hit(by_id[h.chunk_id], rank, h.score, "keyword")
        for rank, h in enumerate(index.search(query, k), start=1)
    ]
