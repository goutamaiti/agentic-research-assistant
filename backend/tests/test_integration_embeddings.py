"""Opt-in integration test with the real Sentence Transformers model.

Run with:  RUN_INTEGRATION=1 .venv/Scripts/python -m pytest -m integration -q
The first run downloads ``multi-qa-mpnet-base-cos-v1`` (~420 MB) from Hugging Face.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.retrieval.embeddings import SentenceTransformerEmbedder
from app.services.retrieval_service import search_keyword, search_semantic
from tests.conftest import make_client, make_settings
from tests.pdf_factory import write_paper

pytestmark = pytest.mark.integration

MODEL_ID = "sentence-transformers/multi-qa-mpnet-base-cos-v1"


@pytest.fixture(scope="module")
def embedder() -> SentenceTransformerEmbedder:
    return SentenceTransformerEmbedder(MODEL_ID)


def test_real_model_properties(embedder: SentenceTransformerEmbedder) -> None:
    assert embedder.max_seq_length >= 384
    vector = embedder.embed_query("What dataset was used?")
    assert len(vector) == 768
    assert abs(sum(v * v for v in vector) - 1.0) < 1e-3  # normalised for cosine


def test_index_and_search_with_real_model(
    tmp_path: Path, embedder: SentenceTransformerEmbedder
) -> None:
    settings = make_settings(tmp_path)
    paper = write_paper(tmp_path / "paper.pdf", extra_paragraphs=12)
    with make_client(settings, embedder=embedder) as client:
        upload = client.post(
            "/api/documents/upload", files={"file": ("paper.pdf", paper.read_bytes())}
        )
        document_id = upload.json()["id"]
        client.post(f"/api/documents/{document_id}/analyze")
        status = client.get(f"/api/documents/{document_id}/status").json()
        assert status["status"] == "indexed", status
        indexing = next(s for s in status["stages"] if s["stage"] == "retrieval_indexing")
        # Chunk sizes are measured with the model's own tokenizer and respect the cap.
        assert indexing["metrics"]["tokens_max"] <= settings.chunk_max_tokens
        assert indexing["metrics"]["embedding_model_id"] == MODEL_ID

        factory = client.app.state.session_factory
        with factory() as session:
            # A paraphrased question (few shared words) should still find the results text.
            semantic = search_semantic(
                session,
                client.app.state.chroma_client,
                embedder,
                document_id,
                "How much better was the combined retriever than each single method?",
                3,
            )
            keyword = search_keyword(session, document_id, "reciprocal rank fusion", 3)
    assert any(hit.section_type == "results" for hit in semantic)
    assert keyword and keyword[0].section_type == "methodology"
