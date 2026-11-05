"""End-to-end tests of the document and analysis HTTP API (Phase 2)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.database.models import (
    Document,
    DocumentChunk,
    DocumentStatus,
    ProcessingRun,
    RunStatus,
)
from app.errors import AppError
from app.services.analysis_service import STAGES
from app.services.retrieval_service import search_keyword, search_semantic
from tests import pdf_factory
from tests.conftest import make_client, make_settings
from tests.fakes import FakeEmbedder, FakeOcr


def _upload(client: TestClient, path: Path, name: str | None = None) -> Any:
    with path.open("rb") as handle:
        return client.post(
            "/api/documents/upload",
            files={"file": (name or path.name, handle, "application/pdf")},
        )


def _upload_bytes(client: TestClient, data: bytes, name: str = "x.pdf") -> Any:
    return client.post("/api/documents/upload", files={"file": (name, data, "application/pdf")})


def _pdf_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "pdfs"
    directory.mkdir(exist_ok=True)
    return directory


def _paper(tmp_path: Path, name: str = "paper.pdf", **kwargs: Any) -> Path:
    return pdf_factory.write_paper(_pdf_dir(tmp_path) / name, **kwargs)


def _analyzed(client: TestClient, path: Path) -> str:
    response = _upload(client, path)
    assert response.status_code == 201, response.text
    document_id = response.json()["id"]
    analyze = client.post(f"/api/documents/{document_id}/analyze")
    assert analyze.status_code == 202, analyze.text
    return document_id


def _stages(client: TestClient, document_id: str) -> dict[str, dict[str, Any]]:
    body = client.get(f"/api/documents/{document_id}/status").json()
    return {stage["stage"]: stage for stage in body["stages"]}


def _error(response: Any) -> dict[str, Any]:
    return response.json()["error"]


# ----- Upload ---------------------------------------------------------------------------


def test_upload_returns_summary(client: TestClient, tmp_path: Path) -> None:
    path = _paper(tmp_path)
    response = _upload(client, path)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "uploaded"
    assert body["original_filename"] == "paper.pdf"
    assert body["page_count"] >= 3
    assert body["file_size"] == path.stat().st_size

    assert body["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert body["title"] is None  # not guessed before analysis


def test_duplicate_upload_points_to_first_document(client: TestClient, tmp_path: Path) -> None:
    path = _paper(tmp_path)
    first = _upload(client, path).json()
    response = _upload(client, path, name="copy.pdf")
    assert response.status_code == 409
    error = _error(response)
    assert error["code"] == "duplicate_document"
    assert error["details"]["document_id"] == first["id"]
    assert len(client.get("/api/documents").json()) == 1


@pytest.mark.parametrize(
    ("writer", "status", "code"),
    [
        (pdf_factory.write_encrypted_pdf, 422, "encrypted_pdf"),
        (pdf_factory.write_corrupt_pdf, 422, "corrupt_pdf"),
    ],
)
def test_upload_rejects_invalid_pdfs(
    client: TestClient, tmp_path: Path, writer: Any, status: int, code: str
) -> None:
    path = writer(_pdf_dir(tmp_path) / "bad.pdf")
    response = _upload(client, path)
    assert response.status_code == status
    assert _error(response)["code"] == code
    assert client.get("/api/documents").json() == []


def test_upload_rejects_non_pdf_named_pdf(client: TestClient) -> None:
    response = _upload_bytes(client, b"Hello, this is plain text, not a PDF at all.\n")
    assert response.status_code == 415
    assert _error(response)["code"] == "not_pdf"


def test_upload_rejects_empty_file(client: TestClient) -> None:
    response = _upload_bytes(client, b"")
    assert response.status_code == 400
    assert _error(response)["code"] == "empty_file"


def test_upload_rejects_file_over_limit(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, max_upload_mb=1)
    with make_client(settings) as client:
        data = b"%PDF-1.7\n" + b"0" * (1024 * 1024 + 16)
        response = _upload_bytes(client, data)
        assert response.status_code == 413
        assert _error(response)["code"] == "file_too_large"
        assert list(settings.uploads_path.iterdir()) == []


def test_unsafe_filename_is_sanitised_and_file_stored_by_id(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    response = _upload(client, _paper(tmp_path), name="../../evil<>.pdf")
    assert response.status_code == 201
    body = response.json()
    name = body["original_filename"]
    assert "/" not in name and "\\" not in name and "<" not in name and ">" not in name
    assert ".." not in name
    assert name.endswith(".pdf")
    stored = sorted(p.name for p in settings.uploads_path.iterdir())
    assert stored == [f"{body['id']}.pdf"]
    assert not list(settings.storage_path.rglob("*.part"))
    assert not list(tmp_path.glob("evil*"))


def test_list_and_detail_not_found(client: TestClient, tmp_path: Path) -> None:
    first = _upload(client, _paper(tmp_path)).json()
    second = _upload(client, _paper(tmp_path, "b.pdf", extra_paragraphs=1)).json()
    listed = client.get("/api/documents")
    assert listed.status_code == 200
    assert {d["id"] for d in listed.json()} == {first["id"], second["id"]}

    for bad_id in ("0" * 32, "not-a-valid-id", "ABCDEF" * 5 + "00"):
        response = client.get(f"/api/documents/{bad_id}")
        assert response.status_code == 404
        assert _error(response)["code"] == "document_not_found"


def test_detail_before_analysis_has_no_guessed_data(client: TestClient, tmp_path: Path) -> None:
    document_id = _upload(client, _paper(tmp_path)).json()["id"]
    body = client.get(f"/api/documents/{document_id}").json()
    assert body["metadata"] is None
    assert body["pages"] == []
    assert body["sections"] == []
    assert body["index"]["chunks_total"] == 0
    assert body["index"]["embedding_model_id"] is None
    status = client.get(f"/api/documents/{document_id}/status").json()
    assert status["workflow_run_id"] is None
    assert status["stages"] == []


# ----- Analysis -------------------------------------------------------------------------


def test_analyze_indexes_paper(client: TestClient, tmp_path: Path) -> None:
    document_id = _upload(client, _paper(tmp_path)).json()["id"]
    response = client.post(f"/api/documents/{document_id}/analyze")
    assert response.status_code == 202
    body = response.json()
    assert body["document_id"] == document_id
    assert body["status"] == "indexed"  # InlineJobRunner runs synchronously

    status = client.get(f"/api/documents/{document_id}/status").json()
    assert status["status"] == "indexed"
    assert status["workflow_run_id"] == body["workflow_run_id"]
    assert [s["stage"] for s in status["stages"]] == list(STAGES)
    by_stage = {s["stage"]: s for s in status["stages"]}
    processing_stages = [by_stage[name] for name in STAGES if name != "knowledge_extraction"]
    assert all(s["status"] == "completed" for s in processing_stages)
    assert all(s["started_at"] and s["completed_at"] for s in processing_stages)
    # No LLM is configured in this client, so extraction is skipped with a reason.
    assert by_stage["knowledge_extraction"]["status"] == "skipped"
    assert by_stage["knowledge_extraction"]["metrics"]["reason"] == "llm_not_configured"
    assert "extraction skipped" in status["status_detail"]
    indexing = {s["stage"]: s for s in status["stages"]}["retrieval_indexing"]["metrics"]
    assert indexing["chunks_indexed"] > 0
    assert indexing["vectors_stored"] == indexing["chunks_indexed"]
    assert indexing["embedding_model_id"] == FakeEmbedder.model_id


def test_detail_after_analysis(client: TestClient, tmp_path: Path) -> None:
    document_id = _analyzed(client, _paper(tmp_path))
    body = client.get(f"/api/documents/{document_id}").json()

    pages = body["pages"]
    assert [p["pdf_page_index"] for p in pages] == list(range(body["page_count"]))
    assert [p["displayed_page_number"] for p in pages] == [str(101 + i) for i in range(len(pages))]
    assert all(p["extraction_status"] == "extracted" and not p["ocr_used"] for p in pages)

    titles = [s["title"] for s in body["sections"]]
    for heading in ("Introduction", "Related Work", "Methodology", "Results", "References"):
        assert any(heading in t for t in titles), (heading, titles)
    sub = next(s for s in body["sections"] if "Data Preprocessing" in s["title"])
    assert sub["level"] == 2
    parent = next(s for s in body["sections"] if s["section_index"] == sub["parent_index"])
    assert "Methodology" in parent["title"]

    assert body["metadata"]["doi"]["value"] == pdf_factory.DOI
    assert body["title"] == pdf_factory.TITLE
    index = body["index"]
    assert index["embedding_model_id"] == FakeEmbedder.model_id
    assert index["index_version"]
    assert 0 < index["chunks_indexed"] < index["chunks_total"]  # references kept, not indexed


def test_reference_chunks_are_kept_but_not_indexed(client: TestClient, tmp_path: Path) -> None:
    document_id = _analyzed(client, _paper(tmp_path))
    with client.app.state.session_factory() as session:
        chunks = session.scalars(
            select(DocumentChunk).where(DocumentChunk.document_id == document_id)
        ).all()
    references = [c for c in chunks if c.section_type == "references"]
    assert references
    assert all(not c.indexed for c in references)
    assert all(c.indexed for c in chunks if c.section_type not in ("references",))


def test_search_returns_this_documents_chunks_with_provenance(
    client: TestClient, tmp_path: Path
) -> None:
    document_id = _analyzed(client, _paper(tmp_path))
    state = client.app.state
    with state.session_factory() as session:
        semantic = search_semantic(
            session, state.chroma_client, state.embedder, document_id, "hybrid retriever recall", 5
        )
        keyword = search_keyword(session, document_id, "BM25 term frequency", 5)
    assert semantic and keyword
    for hit in semantic + keyword:
        assert hit.chunk_id.startswith(document_id)
        assert hit.section_name
        assert hit.pdf_page_start <= hit.pdf_page_end
        assert hit.displayed_page_start == str(101 + hit.pdf_page_start)
        assert hit.section_type != "references"
    assert [h.rank for h in keyword] == list(range(1, len(keyword) + 1))
    assert "BM25" in keyword[0].text


def test_searches_are_isolated_per_document(client: TestClient, tmp_path: Path) -> None:
    first = _analyzed(client, _paper(tmp_path))
    second = _analyzed(client, _paper(tmp_path, "b.pdf", extra_paragraphs=2))
    state = client.app.state
    with state.session_factory() as session:
        for document_id in (first, second):
            semantic = search_semantic(
                session, state.chroma_client, state.embedder, document_id, "dense retrieval", 50
            )
            keyword = search_keyword(session, document_id, "dense retrieval passages", 50)
            assert semantic and keyword
            assert all(h.chunk_id.startswith(document_id) for h in semantic + keyword)


def test_reanalysis_is_idempotent(client: TestClient, tmp_path: Path) -> None:
    document_id = _analyzed(client, _paper(tmp_path))
    before = client.get(f"/api/documents/{document_id}").json()
    again = client.post(f"/api/documents/{document_id}/analyze")
    assert again.status_code == 202
    after = client.get(f"/api/documents/{document_id}").json()
    assert after["status"] == "indexed"
    assert after["index"] == before["index"]
    assert len(after["pages"]) == len(before["pages"])
    assert after["sections"] == before["sections"]
    metrics = _stages(client, document_id)["retrieval_indexing"]["metrics"]
    assert metrics["vectors_stored"] == before["index"]["chunks_indexed"]
    with client.app.state.session_factory() as session:
        ids = session.scalars(
            select(DocumentChunk.chunk_id).where(DocumentChunk.document_id == document_id)
        ).all()
    assert len(ids) == len(set(ids)) == before["index"]["chunks_total"]


def test_scanned_pdf_without_ocr_fails_explicitly(client: TestClient, tmp_path: Path) -> None:
    path = pdf_factory.write_scanned_pdf(_pdf_dir(tmp_path) / "scan.pdf", pages=2)
    document_id = _analyzed(client, path)
    status = client.get(f"/api/documents/{document_id}/status").json()
    assert status["status"] == "failed"
    assert status["status_detail"]
    stages = {s["stage"]: s for s in status["stages"]}
    assert stages["upload_validation"]["status"] == "completed"
    assert stages["document_extraction"]["status"] == "failed"
    assert stages["document_extraction"]["error"]["code"] == "no_extractable_text"
    assert stages["section_identification"]["status"] == "skipped"
    assert stages["retrieval_indexing"]["status"] == "skipped"
    detail = client.get(f"/api/documents/{document_id}").json()
    assert detail["index"]["chunks_total"] == 0


def test_mixed_pdf_without_ocr_is_partially_indexed(client: TestClient, tmp_path: Path) -> None:
    document_id = _analyzed(client, pdf_factory.write_mixed_pdf(_pdf_dir(tmp_path) / "mix.pdf"))
    detail = client.get(f"/api/documents/{document_id}").json()
    assert detail["status"] == "partially_indexed"
    last = detail["pages"][-1]
    assert last["extraction_status"] == "ocr_unavailable"
    assert not last["ocr_used"]
    assert last["char_count"] == 0
    extraction = _stages(client, document_id)["document_extraction"]
    assert extraction["status"] == "partial"
    assert extraction["metrics"]["unreadable_pages"] == [last["pdf_page_index"]]
    assert extraction["metrics"]["ocr_available"] is False
    assert detail["index"]["chunks_indexed"] > 0


def test_mixed_pdf_with_ocr_is_indexed(settings: Settings, tmp_path: Path) -> None:
    ocr = FakeOcr()
    with make_client(settings, ocr_engine=ocr) as client:
        path = pdf_factory.write_mixed_pdf(_pdf_dir(tmp_path) / "mix.pdf")
        document_id = _analyzed(client, path)
        detail = client.get(f"/api/documents/{document_id}").json()
        extraction = _stages(client, document_id)["document_extraction"]
    assert detail["status"] == "indexed"
    last = detail["pages"][-1]
    assert last["extraction_status"] == "ocr_extracted"
    assert last["ocr_used"] is True
    assert last["char_count"] > 0
    assert all(not p["ocr_used"] for p in detail["pages"][:-1])
    assert extraction["status"] == "completed"
    assert extraction["metrics"]["ocr_pages"] == [last["pdf_page_index"]]
    assert ocr.calls == 1


def test_embedding_failure_marks_document_failed(settings: Settings, tmp_path: Path) -> None:
    with make_client(settings, embedder=FakeEmbedder(fail=True)) as client:
        document_id = _analyzed(client, _paper(tmp_path))
        status = client.get(f"/api/documents/{document_id}/status").json()
        detail = client.get(f"/api/documents/{document_id}").json()
        state = client.app.state
        with state.session_factory() as session:
            with pytest.raises(AppError) as semantic_error:
                search_semantic(session, state.chroma_client, state.embedder, document_id, "x", 3)
            with pytest.raises(AppError) as keyword_error:
                search_keyword(session, document_id, "retrieval", 3)
    assert status["status"] == "failed"
    stages = {s["stage"]: s for s in status["stages"]}
    assert stages["retrieval_indexing"]["status"] == "failed"
    assert stages["retrieval_indexing"]["error"]["code"] == "embedding_failed"
    assert detail["index"]["chunks_total"] == 0
    for error in (semantic_error.value, keyword_error.value):
        assert error.status_code == 409
        assert error.code == "document_not_indexed"


def test_analyze_while_queued_is_rejected(client: TestClient, tmp_path: Path) -> None:
    document_id = _upload(client, _paper(tmp_path)).json()["id"]
    with client.app.state.session_factory() as session:
        session.get(Document, document_id).status = DocumentStatus.QUEUED
        session.commit()
    response = client.post(f"/api/documents/{document_id}/analyze")
    assert response.status_code == 409
    assert _error(response)["code"] == "analysis_in_progress"


def test_analyze_unknown_document_is_404(client: TestClient) -> None:
    response = client.post(f"/api/documents/{'f' * 32}/analyze")
    assert response.status_code == 404
    assert _error(response)["code"] == "document_not_found"
    assert client.get(f"/api/documents/{'f' * 32}/status").status_code == 404


def test_recover_marks_unfinished_work_interrupted(client: TestClient, tmp_path: Path) -> None:
    queued = _upload(client, _paper(tmp_path)).json()["id"]
    processing = _upload(client, _paper(tmp_path, "b.pdf", extra_paragraphs=1)).json()["id"]
    done = _analyzed(client, _paper(tmp_path, "c.pdf", extra_paragraphs=2))
    with client.app.state.session_factory() as session:
        session.get(Document, queued).status = DocumentStatus.QUEUED
        session.get(Document, processing).status = DocumentStatus.PROCESSING
        for stage, run_status in ((STAGES[0], RunStatus.RUNNING), (STAGES[1], RunStatus.PENDING)):
            session.add(
                ProcessingRun(
                    document_id=processing,
                    workflow_run_id="a" * 32,
                    stage=stage,
                    status=run_status,
                )
            )
        session.commit()

    assert client.app.state.analysis_service.recover() == 2

    with client.app.state.session_factory() as session:
        assert session.get(Document, queued).status == DocumentStatus.FAILED
        assert session.get(Document, processing).status == DocumentStatus.FAILED
        assert session.get(Document, done).status == DocumentStatus.INDEXED
        runs = session.scalars(
            select(ProcessingRun).where(ProcessingRun.workflow_run_id == "a" * 32)
        ).all()
        assert all(r.status == RunStatus.INTERRUPTED for r in runs)
        assert all(r.error_json["code"] == "interrupted" for r in runs)
        completed = session.scalars(
            select(ProcessingRun).where(ProcessingRun.document_id == done)
        ).all()
        # A finished run is left untouched (its skipped extraction stage included).
        assert all(r.status in (RunStatus.COMPLETED, RunStatus.SKIPPED) for r in completed)
        assert sum(r.status == RunStatus.SKIPPED for r in completed) == 1
    stages = _stages(client, processing)
    assert stages[STAGES[0]]["status"] == "interrupted"


def test_health_reports_ocr_and_embeddings(client: TestClient) -> None:
    components = client.get("/api/health").json()["components"]
    assert components["ocr"]["status"] == "not_configured"
    assert components["embeddings"]["status"] == "configured"
    assert FakeEmbedder.model_id in components["embeddings"]["detail"]


def test_health_reports_ocr_ok_when_available(settings: Settings) -> None:
    with make_client(settings, ocr_engine=FakeOcr()) as client:
        components = client.get("/api/health").json()["components"]
    assert components["ocr"]["status"] == "ok"
