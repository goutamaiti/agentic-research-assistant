"""Test doubles for external services (embedding model, OCR, background runner)."""

from __future__ import annotations

import hashlib
import math
import re

from app.document_processing.ocr import OcrError, OcrLine, OcrResult

_WORD = re.compile(r"\w+|[^\w\s]")


class FakeEmbedder:
    """Deterministic hashed bag-of-words vectors: similar wording -> similar vectors.

    Token counting approximates a word-piece tokenizer by counting words and punctuation.
    """

    model_id = "test/fake-hash-embedder"
    dimensions = 256

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    @property
    def max_seq_length(self) -> int:
        return 512

    def count_tokens(self, text: str) -> int:
        return len(_WORD.findall(text))

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            digest = hashlib.md5(word.encode(), usedforsecurity=False).digest()
            vector[digest[0] % self.dimensions] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        from app.retrieval.embeddings import EmbeddingError

        self.calls += 1
        if self.fail:
            raise EmbeddingError("fake embedder failure")
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class FakeOcr:
    """Returns fixed text for every page, as if Tesseract had read it."""

    TEXT = [
        "Scanned page about convolutional networks.",
        "The scanned appendix describes image augmentation with random crops and flips.",
    ]

    def __init__(self, *, available: bool = True, fail: bool = False) -> None:
        self.available = available
        self.fail = fail
        self.calls = 0

    def is_available(self) -> bool:
        return self.available

    def recognize(self, png_bytes: bytes) -> OcrResult:
        assert png_bytes.startswith(b"\x89PNG")
        self.calls += 1
        if self.fail:
            raise OcrError("fake OCR failure")
        lines = [OcrLine(text=t, y0=100 + 40 * i, y1=120 + 40 * i) for i, t in enumerate(self.TEXT)]
        return OcrResult(lines=lines, mean_confidence=91.0)
