"""Embedded, persistent ChromaDB client.

Chroma is used only as an in-process ``PersistentClient``. Do not start a Chroma HTTP
server: chromadb 1.5.9 has open advisories affecting its server endpoints.
Per-document collections and indexing are added in Phase 2.
"""

from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.api import ClientAPI
from chromadb.config import Settings as ChromaSettings


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
