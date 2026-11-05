"""BM25 keyword retrieval over one document's chunks.

The index is built from the chunks stored in SQLite (the source of truth), so it needs no
separate persistence. For a single paper (hundreds of chunks) building it is fast.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

# Keep technical tokens intact: "bert-base", "f1", "gpt-4", "p@k", "1e-5", "3.5".
_TOKEN = re.compile(r"[a-z0-9]+(?:[-_.@/][a-z0-9]+)*")
_PART_SPLIT = re.compile(r"[-_.@/]")
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the this to was "
    "were with we our which these those their been can not".split()
)


def tokenize(text: str) -> list[str]:
    """Lower-cased terms. A compound ("self-attention") yields itself and its word parts
    ("self", "attention"), so both exact and component queries match; numeric parts of
    values like "3.5" are not split out."""
    tokens: list[str] = []
    for token in _TOKEN.findall(text.lower()):
        if token in _STOPWORDS:
            continue
        tokens.append(token)
        if _PART_SPLIT.search(token):
            tokens.extend(
                part
                for part in _PART_SPLIT.split(token)
                if len(part) > 1 and not part.isdigit() and part not in _STOPWORDS
            )
    return tokens


@dataclass(slots=True)
class KeywordHit:
    chunk_id: str
    score: float


class KeywordIndex:
    def __init__(self, chunk_ids: list[str], texts: list[str]) -> None:
        if len(chunk_ids) != len(texts):
            raise ValueError("chunk_ids and texts must have the same length")
        self._chunk_ids = chunk_ids
        self._tokens = [tokenize(text) for text in texts]
        # rank_bm25 cannot build over an empty corpus.
        self._bm25 = BM25Okapi(self._tokens) if any(self._tokens) else None

    def __len__(self) -> int:
        return len(self._chunk_ids)

    def search(self, query: str, k: int) -> list[KeywordHit]:
        query_tokens = tokenize(query)
        if self._bm25 is None or not query_tokens:
            return []
        scores = self._bm25.get_scores(query_tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        # Only chunks that share at least one query term are keyword matches.
        query_set = set(query_tokens)
        return [
            KeywordHit(chunk_id=self._chunk_ids[i], score=float(scores[i]))
            for i in ranked
            if query_set & set(self._tokens[i])
        ][:k]
