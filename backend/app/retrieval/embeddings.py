"""Local embedding generation (Sentence Transformers).

The model is loaded lazily on first use, in the worker that needs it, so API startup and
health checks never download or load it.
"""

from __future__ import annotations

import logging
import threading
from typing import Protocol

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    """The embedding model could not be loaded or failed to encode text."""


class Embedder(Protocol):
    model_id: str

    @property
    def max_seq_length(self) -> int: ...

    def count_tokens(self, text: str) -> int: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class SentenceTransformerEmbedder:
    """``multi-qa-mpnet-base-cos-v1`` produces normalised vectors for cosine similarity."""

    def __init__(self, model_id: str, *, device: str = "cpu", batch_size: int = 16) -> None:
        self.model_id = model_id
        self._device = device
        self._batch_size = batch_size
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    try:
                        from sentence_transformers import SentenceTransformer

                        logger.info("Loading embedding model %s on %s", self.model_id, self._device)
                        self._model = SentenceTransformer(self.model_id, device=self._device)
                    except Exception as exc:
                        raise EmbeddingError(
                            f"Could not load embedding model {self.model_id!r}: "
                            f"{type(exc).__name__}: {exc}"
                        ) from exc
        return self._model

    @property
    def max_seq_length(self) -> int:
        return int(self._load().max_seq_length)

    def count_tokens(self, text: str) -> int:
        tokenizer = self._load().tokenizer
        return len(tokenizer(text, add_special_tokens=False)["input_ids"])

    def _encode(self, texts: list[str]) -> list[list[float]]:
        try:
            vectors = self._load().encode(
                texts,
                batch_size=self._batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError(f"Embedding failed: {type(exc).__name__}") from exc
        return vectors.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts) if texts else []

    def embed_query(self, text: str) -> list[float]:
        return self._encode([text])[0]
