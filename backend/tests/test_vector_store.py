from __future__ import annotations

from pathlib import Path

from app.retrieval.vector_store import check_vector_store, create_chroma_client


def test_persistent_client_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "chroma"
    client = create_chroma_client(path)
    check_vector_store(client)
    assert client.get_settings().anonymized_telemetry is False

    # Embeddings are supplied explicitly (no default embedding function is used).
    collection = client.get_or_create_collection(name="phase1-smoke", embedding_function=None)
    collection.add(
        ids=["chunk-1", "chunk-2"],
        embeddings=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        documents=["first passage", "second passage"],
        metadatas=[{"pdf_page_index": 0}, {"pdf_page_index": 1}],
    )
    result = collection.query(query_embeddings=[[0.9, 0.1, 0.0]], n_results=1)
    assert result["ids"] == [["chunk-1"]]

    # Data persists for a new client on the same path.
    reopened = create_chroma_client(path)
    assert reopened.get_collection("phase1-smoke").count() == 2

    reopened.delete_collection("phase1-smoke")
    assert [c.name for c in reopened.list_collections()] == []
