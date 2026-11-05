"""GET /api/documents/{id}/analysis and the knowledge_extraction stage lifecycle (Phase 3)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.config import INDEX_VERSION, Settings
from app.database.connection import create_db_engine, create_session_factory
from app.database.migrations import alembic_config, upgrade_database
from app.database.models import Document, DocumentStatus, Extraction
from app.prompts.extraction import PROMPT_VERSION
from app.retrieval.vector_store import VectorStoreError
from app.schemas.evidence import QuoteMatch
from app.schemas.extraction import SCHEMA_VERSION, ExtractionResult
from app.services import analysis_service as analysis_module
from app.services.llm_service import LLMService
from app.services.retrieval_service import SEARCHABLE_STATUSES, search_keyword
from tests import pdf_factory
from tests.conftest import make_client, make_settings
from tests.fakes import FakeEmbedder, FakeLLMTransport, grounded_responder

API_KEY = "test-key-not-real"


def _llm(transport: FakeLLMTransport | None = None) -> LLMService:
    return LLMService(
        transport or FakeLLMTransport(grounded_responder),
        model_id="fake-model",
        sleep=lambda s: None,
    )


def _pdf_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "pdfs"
    directory.mkdir(exist_ok=True)
    return directory


def _paper(tmp_path: Path) -> Path:
    return pdf_factory.write_paper(_pdf_dir(tmp_path) / "paper.pdf")


def _upload(client: TestClient, path: Path) -> str:
    with path.open("rb") as handle:
        response = client.post(
            "/api/documents/upload", files={"file": (path.name, handle, "application/pdf")}
        )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _analyze(client: TestClient, document_id: str) -> str:
    response = client.post(f"/api/documents/{document_id}/analyze")
    assert response.status_code == 202, response.text
    return response.json()["workflow_run_id"]


def _status(client: TestClient, document_id: str) -> dict[str, Any]:
    response = client.get(f"/api/documents/{document_id}/status")
    assert response.status_code == 200, response.text
    return response.json()


def _stages(client: TestClient, document_id: str) -> dict[str, dict[str, Any]]:
    return {stage["stage"]: stage for stage in _status(client, document_id)["stages"]}


def _extractions(client: TestClient, document_id: str) -> list[Extraction]:
    with client.app.state.session_factory() as session:
        rows = session.scalars(
            select(Extraction).where(Extraction.document_id == document_id)
        ).all()
        session.expunge_all()
    return list(rows)


def _search_works(client: TestClient, document_id: str) -> None:
    with client.app.state.session_factory() as session:
        hits = search_keyword(session, document_id, "BM25 retrieval", 5)
    assert hits
    assert all(hit.chunk_id.startswith(document_id) for hit in hits)


# ----- Without an LLM -------------------------------------------------------------------


def test_without_llm_extraction_is_skipped_and_analysis_404(
    client: TestClient, tmp_path: Path
) -> None:
    document_id = _upload(client, _paper(tmp_path))
    _analyze(client, document_id)
    status = _status(client, document_id)
    assert status["status"] == "indexed"
    assert "skipped" in status["status_detail"].lower()
    stage = _stages(client, document_id)["knowledge_extraction"]
    assert stage["status"] == "skipped"
    assert stage["metrics"]["reason"] == "llm_not_configured"
    assert stage["error"] is None

    response = client.get(f"/api/documents/{document_id}/analysis")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "analysis_not_found"
    assert error["details"] == {"status": "indexed"}
    assert _extractions(client, document_id) == []


def test_analysis_of_unknown_document_is_404(client: TestClient) -> None:
    response = client.get(f"/api/documents/{'0' * 32}/analysis")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "document_not_found"


def test_analysis_before_any_run_is_404(client: TestClient, tmp_path: Path) -> None:
    document_id = _upload(client, _paper(tmp_path))
    response = client.get(f"/api/documents/{document_id}/analysis")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "analysis_not_found"
    assert error["details"] == {"status": "uploaded"}


# ----- With an LLM ----------------------------------------------------------------------


def test_analysis_with_llm_returns_validated_result(settings: Settings, tmp_path: Path) -> None:
    transport = FakeLLMTransport(grounded_responder)
    with make_client(settings, llm_service=_llm(transport)) as client:
        document_id = _upload(client, _paper(tmp_path))
        run_id = _analyze(client, document_id)
        status = _status(client, document_id)
        assert status["status"] == "analyzed"
        assert status["workflow_run_id"] == run_id

        response = client.get(f"/api/documents/{document_id}/analysis")
        assert response.status_code == 200, response.text
        body = response.json()
        rows = _extractions(client, document_id)

    assert len(rows) == 1
    row = rows[0]
    assert body["document_id"] == document_id
    assert body["extraction_id"] == row.id
    assert body["status"] == "completed"
    created = datetime.fromisoformat(body["created_at"])
    assert created.utcoffset() == timedelta(0)

    result = ExtractionResult.model_validate(body["result"])
    meta = result.processing_metadata
    assert meta.document_id == document_id
    assert meta.workflow_run_id == run_id
    assert meta.processing_status == "completed"
    assert meta.model_id == "fake-model"
    assert meta.prompt_version == PROMPT_VERSION
    assert result.schema_version == SCHEMA_VERSION
    assert {t.task for t in meta.tasks} == set(FakeLLMTransport.TASKS.values())
    assert all(t.task_status != "failed" for t in meta.tasks)
    # The stored row is the same validated result the endpoint returned.
    assert ExtractionResult.model_validate(row.result_json) == result
    assert row.status == "completed"
    assert row.workflow_run_id == run_id
    assert len(transport.calls) == len(FakeLLMTransport.TASKS)


def test_extraction_row_records_versions(settings: Settings, tmp_path: Path) -> None:
    with make_client(settings, llm_service=_llm()) as client:
        document_id = _upload(client, _paper(tmp_path))
        _analyze(client, document_id)
        rows = _extractions(client, document_id)
    assert len(rows) == 1
    row = rows[0]
    assert row.model_id == "fake-model"
    assert row.prompt_version == PROMPT_VERSION
    assert row.schema_version == SCHEMA_VERSION
    assert row.index_version == INDEX_VERSION
    assert row.embedding_model_id == FakeEmbedder.model_id
    assert row.created_at.utcoffset() == timedelta(0)


def test_extraction_stage_metrics(settings: Settings, tmp_path: Path) -> None:
    transport = FakeLLMTransport(grounded_responder)
    with make_client(settings, llm_service=_llm(transport)) as client:
        document_id = _upload(client, _paper(tmp_path))
        _analyze(client, document_id)
        stage = _stages(client, document_id)["knowledge_extraction"]
        result = ExtractionResult.model_validate(
            client.get(f"/api/documents/{document_id}/analysis").json()["result"]
        )

    assert stage["status"] == "completed"
    assert stage["started_at"] is not None
    assert stage["completed_at"] is not None
    metrics = stage["metrics"]
    assert metrics["model_id"] == "fake-model"
    assert metrics["prompt_version"] == PROMPT_VERSION
    assert metrics["schema_version"] == SCHEMA_VERSION
    # One call per task: every answer was valid on the first attempt.
    assert metrics["llm_calls"] == len(transport.calls) == len(FakeLLMTransport.TASKS)
    expected_in = sum(len(call["prompt"]) // 4 for call in transport.calls)
    assert metrics["input_tokens"] == expected_in > 0
    assert metrics["output_tokens"] > 0
    assert metrics["claims"] == len(result.claims) > 0
    assert metrics["evidence_records"] == len(result.evidence_registry) > 0
    matches = metrics["evidence_quote_match"]
    assert set(matches) <= {m.value for m in QuoteMatch}
    assert sum(matches.values()) == len(result.evidence_registry)
    assert matches.get(QuoteMatch.EXACT.value, 0) > 0
    assert isinstance(metrics["duration_ms"], int)
    assert len(metrics["tasks"]) == len(FakeLLMTransport.TASKS)


def test_analysis_result_drops_traps(settings: Settings, tmp_path: Path) -> None:
    with make_client(settings, llm_service=_llm()) as client:
        document_id = _upload(client, _paper(tmp_path))
        _analyze(client, document_id)
        body = client.get(f"/api/documents/{document_id}/analysis").json()
    result = ExtractionResult.model_validate(body["result"])
    dumped = str(body["result"])
    # Unsupported venue and fabricated injected IDs never reach the stored result.
    assert "Imaginary Conference" not in dumped
    assert "CLM_999" not in dumped
    assert "Only one dataset was used." not in dumped
    # A quote that is not in the paper never gets a page citation.
    for record in result.evidence_registry:
        if "best ever published anywhere" in record.source_text:
            assert record.quote_match == QuoteMatch.NOT_FOUND
        if record.quote_match == QuoteMatch.NOT_FOUND:
            assert record.pdf_page_index is None
            assert record.chunk_id is None
        elif record.quote_match != QuoteMatch.PDF_METADATA:
            # Traceable to a page (and to a chunk of this document when one is cited).
            assert record.pdf_page_index is not None
            assert record.chunk_id is None or record.chunk_id.startswith(document_id)
    assert any(record.chunk_id for record in result.evidence_registry)
    # Every claim links only to evidence that exists in the registry.
    evidence_ids = {record.evidence_id for record in result.evidence_registry}
    claim_ids = {claim.claim_id for claim in result.claims}
    for claim in result.claims:
        assert set(claim.evidence_ids) <= evidence_ids
    for record in result.evidence_registry:
        assert record.claim_id in claim_ids


def test_reanalysis_keeps_exactly_one_extraction(settings: Settings, tmp_path: Path) -> None:
    with make_client(settings, llm_service=_llm()) as client:
        document_id = _upload(client, _paper(tmp_path))
        first_run = _analyze(client, document_id)
        first = _extractions(client, document_id)
        second_run = _analyze(client, document_id)
        second = _extractions(client, document_id)
        body = client.get(f"/api/documents/{document_id}/analysis").json()
        assert _status(client, document_id)["status"] == "analyzed"

    assert first_run != second_run
    assert len(first) == 1
    assert first[0].workflow_run_id == first_run
    assert len(second) == 1
    assert second[0].workflow_run_id == second_run
    assert body["extraction_id"] == second[0].id
    assert body["result"]["processing_metadata"]["workflow_run_id"] == second_run


def test_fatal_failure_on_rerun_removes_analysis(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(settings, llm_service=_llm()) as client:
        document_id = _upload(client, _paper(tmp_path))
        _analyze(client, document_id)
        assert len(_extractions(client, document_id)) == 1

        def broken_index(*args: object, **kwargs: object) -> int:
            raise VectorStoreError("fake vector store failure")

        monkeypatch.setattr(analysis_module, "index_document", broken_index)
        _analyze(client, document_id)

        status = _status(client, document_id)
        stages = {s["stage"]: s for s in status["stages"]}
        assert status["status"] == "failed"
        assert stages["retrieval_indexing"]["status"] == "failed"
        assert stages["retrieval_indexing"]["error"]["code"] == "vector_indexing_failed"
        assert stages["knowledge_extraction"]["status"] == "skipped"
        assert _extractions(client, document_id) == []

        response = client.get(f"/api/documents/{document_id}/analysis")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "analysis_not_found"
        assert response.json()["error"]["details"] == {"status": "failed"}


def test_unexpected_extraction_error_keeps_document_indexed(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(settings, llm_service=_llm()) as client:
        agent = client.app.state.analysis_service.extraction_agent
        assert agent is not None

        def explode(*args: object, **kwargs: object) -> ExtractionResult:
            raise RuntimeError("secret internal detail")

        monkeypatch.setattr(agent, "extract", explode)
        document_id = _upload(client, _paper(tmp_path))
        _analyze(client, document_id)

        status = _status(client, document_id)
        stages = {s["stage"]: s for s in status["stages"]}
        assert status["status"] == "indexed"
        assert "failed" in status["status_detail"].lower()
        assert stages["retrieval_indexing"]["status"] == "completed"
        stage = stages["knowledge_extraction"]
        assert stage["status"] == "failed"
        assert stage["error"]["code"] == "internal_error"
        assert "secret internal detail" not in str(stage["error"])
        assert stage["completed_at"] is not None
        assert _extractions(client, document_id) == []
        response = client.get(f"/api/documents/{document_id}/analysis")
        assert response.status_code == 404
        _search_works(client, document_id)


def test_mixed_pdf_without_ocr_is_partially_analyzed(settings: Settings, tmp_path: Path) -> None:
    with make_client(settings, llm_service=_llm()) as client:
        path = pdf_factory.write_mixed_pdf(_pdf_dir(tmp_path) / "mix.pdf")
        document_id = _upload(client, path)
        _analyze(client, document_id)
        status = _status(client, document_id)
        stages = {s["stage"]: s for s in status["stages"]}
        response = client.get(f"/api/documents/{document_id}/analysis")
        _search_works(client, document_id)

    assert status["status"] == "partially_analyzed"
    assert "could not be read" in status["status_detail"]
    assert stages["document_extraction"]["status"] == "partial"
    assert stages["knowledge_extraction"]["status"] == "completed"
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_analyzed_document_is_searchable(settings: Settings, tmp_path: Path) -> None:
    assert DocumentStatus.ANALYZED in SEARCHABLE_STATUSES
    assert DocumentStatus.PARTIALLY_ANALYZED in SEARCHABLE_STATUSES
    with make_client(settings, llm_service=_llm()) as client:
        document_id = _upload(client, _paper(tmp_path))
        _analyze(client, document_id)
        assert _status(client, document_id)["status"] == "analyzed"
        _search_works(client, document_id)


# ----- Migration ------------------------------------------------------------------------


def _document_row() -> Document:
    return Document(
        id="a" * 32,
        original_filename="paper.pdf",
        stored_filename=f"{'a' * 32}.pdf",
        file_path=f"uploads/{'a' * 32}.pdf",
        sha256="b" * 64,
        file_size=10,
    )


def test_migration_accepts_analysis_statuses_and_downgrades(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'migrate.db').as_posix()}"
    upgrade_database(url)
    engine = create_db_engine(url)
    try:
        assert "extractions" in inspect(engine).get_table_names()
        with create_session_factory(engine)() as session:
            session.add(_document_row())
            session.commit()
        with engine.begin() as connection:
            connection.execute(text("UPDATE documents SET status = 'analyzed'"))
        with engine.begin() as connection, pytest.raises(IntegrityError):
            connection.execute(text("UPDATE documents SET status = 'bogus'"))
        with engine.connect() as connection:
            assert connection.execute(text("SELECT status FROM documents")).scalar() == "analyzed"
    finally:
        engine.dispose()

    command.downgrade(alembic_config(url), "9354e57a3371")
    engine = create_db_engine(url)
    try:
        assert "extractions" not in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.execute(text("SELECT status FROM documents")).scalar() == "indexed"
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "9354e57a3371"
        # The old constraint no longer accepts the analysis statuses.
        with engine.begin() as connection, pytest.raises(IntegrityError):
            connection.execute(text("UPDATE documents SET status = 'analyzed'"))
    finally:
        engine.dispose()


# ----- Secrets --------------------------------------------------------------------------


def test_api_key_never_appears_in_responses(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, gemini_api_key=API_KEY)
    with make_client(settings, llm_service=_llm()) as client:
        document_id = _upload(client, _paper(tmp_path))
        _analyze(client, document_id)
        responses = [
            client.get(f"/api/documents/{document_id}/analysis"),
            client.get(f"/api/documents/{document_id}/status"),
            client.get("/api/health"),
            client.get(f"/api/documents/{document_id}"),
        ]
    for response in responses:
        assert response.status_code == 200, response.text
        assert API_KEY not in response.text
    assert responses[2].json()["components"]["llm"]["status"] == "configured"
