"""Embedded, persistent ChromaDB vector store.

Chroma is used only as an in-process ``PersistentClient``. Do not start a Chroma HTTP
server: chromadb 1.5.9 has open advisories affecting its server endpoints.

Each document gets its own collection, so papers are never mixed in one index.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api import ClientAPI
from chromadb.config import Settings as ChromaSettings
from chromadb.errors import NotFoundError

_DOCUMENT_ID = re.compile(r"^[0-9a-f]{32}$")


class VectorStoreError(RuntimeError):
    """Indexing or querying the vector store failed."""


@dataclass(slots=True)
class VectorRecord:
    chunk_id: str
    text: str
    embedding: list[float]
    metadata: dict[str, str | int | float | bool]


@dataclass(slots=True)
class VectorHit:
    chunk_id: str
    text: str
    distance: float  # cosine distance (0 = identical direction)
    metadata: dict[str, Any]


def create_chroma_client(path: Path, *, anonymized_telemetry: bool = False) -> ClientAPI:
    """Create a persistent Chroma client rooted at ``path`` (created if missing)."""
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(path),
        settings=ChromaSettings(anonymized_telemetry=anonymized_telemetry, allow_reset=False),
    )


def check_vector_store(client: ClientAPI) -> None:
    """Raise if the vector store does not respond."""
    client.heartbeat()


def collection_name(document_id: str) -> str:
    if not _DOCUMENT_ID.match(document_id):
        raise ValueError("document_id must be a 32-character lowercase hex id")
    return f"doc_{document_id}"


def delete_document_vectors(client: ClientAPI, document_id: str) -> None:
    try:
        client.delete_collection(collection_name(document_id))
    except NotFoundError:
        pass


def index_document(
    client: ClientAPI,
    document_id: str,
    records: list[VectorRecord],
    *,
    index_version: str,
    embedding_model_id: str,
) -> int:
    """Replace the document's collection with ``records``; return the stored count."""
    try:
        delete_document_vectors(client, document_id)
        collection = client.create_collection(
            name=collection_name(document_id),
            embedding_function=None,
            configuration={"hnsw": {"space": "cosine"}},
            metadata={
                "document_id": document_id,
                "index_version": index_version,
                "embedding_model_id": embedding_model_id,
            },
        )
        if records:
            collection.add(
                ids=[r.chunk_id for r in records],
                embeddings=[r.embedding for r in records],
                documents=[r.text for r in records],
                metadatas=[r.metadata for r in records],
            )
        return collection.count()
    except ValueError:
        raise
    except Exception as exc:
        raise VectorStoreError(f"Vector indexing failed: {type(exc).__name__}: {exc}") from exc


def semantic_search(
    client: ClientAPI,
    document_id: str,
    query_embedding: list[float],
    k: int,
    *,
    where: dict[str, Any] | None = None,
) -> list[VectorHit]:
    try:
        collection = client.get_collection(collection_name(document_id))
        count = collection.count()
        if count == 0:
            return []
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(k, count),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except NotFoundError as exc:
        raise VectorStoreError("This document has not been indexed.") from exc
    except Exception as exc:
        raise VectorStoreError(f"Vector search failed: {type(exc).__name__}") from exc
    return [
        VectorHit(chunk_id=cid, text=text, distance=float(dist), metadata=dict(meta or {}))
        for cid, text, dist, meta in zip(
            result["ids"][0],
            result["documents"][0],
            result["distances"][0],
            result["metadatas"][0],
            strict=True,
        )
    ]
