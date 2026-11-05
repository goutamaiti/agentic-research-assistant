"""Step 6: hybrid retrieval (RRF), the research assistant, and JSON/PDF reports."""

from __future__ import annotations

import re
from pathlib import Path

from app.retrieval.hybrid_search import reciprocal_rank_fusion
from app.services.llm_service import LLMService
from tests.conftest import make_client, make_settings
from tests.fakes import FakeLLMTransport, grounded_responder
from tests.pdf_factory import write_paper


def test_rrf_rewards_agreement() -> None:
    fused = dict(reciprocal_rank_fusion([["a", "b", "c"], ["b", "d"]]))
    assert max(fused, key=fused.get) == "b"  # ranked by both retrievers
    assert fused["a"] > fused["d"]  # rank 1 in one list beats rank 2 in one list


def _responder(cite: str | None):
    def responder(task, prompt, schema):
        if task == "assistant":
            ids = re.findall(r'<passage id="(P\d+)"', prompt)
            cited = [cite or ids[0]] if ids else []
            return {
                "answer": "The hybrid retriever reached recall at five of 0.82.",
                "cited_passage_ids": cited,
                "insufficient_evidence": False,
                "general_explanation": None,
            }
        return grounded_responder(task, prompt, schema)

    return responder


def _analysed_client(tmp_path: Path, responder):
    llm = LLMService(FakeLLMTransport(responder), model_id="m", sleep=lambda s: None)
    client = make_client(make_settings(tmp_path), llm_service=llm)
    client.__enter__()
    pdf = write_paper(tmp_path / "p.pdf")
    document_id = client.post(
        "/api/documents/upload", files={"file": ("p.pdf", pdf.read_bytes())}
    ).json()["id"]
    client.post(f"/api/documents/{document_id}/analyze")
    return client, document_id


def test_chat_answer_has_validated_page_citations_and_history(tmp_path: Path) -> None:
    client, document_id = _analysed_client(tmp_path, _responder(None))
    try:
        first = client.post(
            f"/api/documents/{document_id}/chat",
            json={"question": "What recall did the hybrid retriever reach?"},
        )
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["insufficient_evidence"] is False
        citation = body["citations"][0]
        assert citation["pdf_page_index"] is not None and citation["text"]
        follow = client.post(
            f"/api/documents/{document_id}/chat",
            json={"question": "And for BM25?", "conversation_id": body["conversation_id"]},
        ).json()
        assert follow["conversation_id"] == body["conversation_id"]
        history = client.get(f"/api/documents/{document_id}/chat/history").json()
        assert [m["role"] for m in history["messages"]] == ["user", "assistant"] * 2
    finally:
        client.__exit__(None, None, None)


def test_invented_citation_becomes_insufficient_evidence(tmp_path: Path) -> None:
    client, document_id = _analysed_client(tmp_path, _responder("P99"))
    try:
        body = client.post(
            f"/api/documents/{document_id}/chat", json={"question": "What recall?"}
        ).json()
        assert body["insufficient_evidence"] is True
        assert body["citations"] == []
        assert "not provide enough evidence" in body["answer"]
    finally:
        client.__exit__(None, None, None)


def test_chat_without_llm_is_503_and_conversations_are_isolated(tmp_path: Path) -> None:
    with make_client(make_settings(tmp_path)) as client:
        pdf = write_paper(tmp_path / "p.pdf")
        document_id = client.post(
            "/api/documents/upload", files={"file": ("p.pdf", pdf.read_bytes())}
        ).json()["id"]
        response = client.post(f"/api/documents/{document_id}/chat", json={"question": "Hi?"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "llm_not_configured"
    client, document_id = _analysed_client(tmp_path / "b", _responder(None))
    try:
        conversation_id = client.post(
            f"/api/documents/{document_id}/chat", json={"question": "Recall?"}
        ).json()["conversation_id"]
        other = client.post(
            "/api/documents/upload",
            files={
                "file": ("q.pdf", write_paper(tmp_path / "q.pdf", extra_paragraphs=2).read_bytes())
            },
        ).json()["id"]
        client.post(f"/api/documents/{other}/analyze")
        response = client.post(
            f"/api/documents/{other}/chat",
            json={"question": "Recall?", "conversation_id": conversation_id},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "conversation_not_found"
    finally:
        client.__exit__(None, None, None)


def test_json_and_pdf_reports_download(tmp_path: Path) -> None:
    client, document_id = _analysed_client(tmp_path, _responder(None))
    try:
        for fmt, magic in (("json", b"{"), ("pdf", b"%PDF")):
            created = client.post(f"/api/documents/{document_id}/report", json={"format": fmt})
            assert created.status_code == 201, created.text
            download = client.get(created.json()["download_url"])
            assert download.status_code == 200
            assert download.content.startswith(magic)
        assert client.get(f"/api/reports/{'0' * 32}").status_code == 404
    finally:
        client.__exit__(None, None, None)
