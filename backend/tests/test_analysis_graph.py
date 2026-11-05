"""The analysis workflow runs as a LangGraph graph with conditional routing."""

from __future__ import annotations

from pathlib import Path

from app.services.analysis_service import _RunContext
from app.workflows.analysis_graph import build_analysis_graph
from tests.conftest import make_client, make_settings
from tests.pdf_factory import write_paper, write_scanned_pdf


def _upload(client, path: Path) -> str:
    return client.post(
        "/api/documents/upload", files={"file": (path.name, path.read_bytes())}
    ).json()["id"]


def test_graph_has_expected_nodes(tmp_path: Path) -> None:
    with make_client(make_settings(tmp_path)) as client:
        service = client.app.state.analysis_service
        graph = build_analysis_graph(service, _RunContext("a" * 32, "b" * 32))
    nodes = set(graph.get_graph().nodes)
    assert {
        "upload_validation",
        "document_extraction",
        "section_identification",
        "retrieval_indexing",
        "knowledge_extraction",
        "finalize",
    } <= nodes


def _invoke(client, document_id: str) -> dict:
    service = client.app.state.analysis_service
    graph = build_analysis_graph(service, _RunContext(document_id, "c" * 32))
    # Stage rows are normally created by start(); create them for this direct run.
    service.start(document_id)
    return graph.invoke({"document_id": document_id, "workflow_run_id": "c" * 32})


def test_successful_run_visits_every_stage_in_order(tmp_path: Path) -> None:
    with make_client(make_settings(tmp_path)) as client:
        document_id = _upload(client, write_paper(tmp_path / "p.pdf"))
        final = _invoke(client, document_id)
    assert final["processing_status"] == "completed"
    assert final["completed_stages"] == [
        "upload_validation",
        "document_extraction",
        "section_identification",
        "retrieval_indexing",
        "knowledge_extraction",
        "evidence_verification",
    ]
    # Only IDs and status travel in the state, never document content.
    assert set(final) <= {
        "document_id",
        "workflow_run_id",
        "current_task",
        "processing_status",
        "processing_errors",
        "completed_stages",
    }


def test_failed_stage_routes_to_end(tmp_path: Path) -> None:
    with make_client(make_settings(tmp_path)) as client:
        # A scanned PDF without OCR has no text: document_extraction fails.
        document_id = _upload(client, write_scanned_pdf(tmp_path / "s.pdf"))
        final = _invoke(client, document_id)
    assert final["processing_status"] == "failed"
    assert final["current_task"] == "document_extraction"
    assert final["completed_stages"] == ["upload_validation"]
    assert final["processing_errors"][0]["code"] == "no_extractable_text"
