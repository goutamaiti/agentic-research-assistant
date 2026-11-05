"""Hybrid retrieval: semantic + BM25 rankings merged with Reciprocal Rank Fusion (spec §6.3)."""

from __future__ import annotations

from chromadb.api import ClientAPI
from sqlalchemy.orm import Session

from app.retrieval.embeddings import Embedder
from app.services.retrieval_service import SearchHit, search_keyword, search_semantic

RRF_K = 60  # standard constant from Cormack et al. (2009)


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Fuse ranked ID lists: score(d) = sum over lists of 1 / (k + rank)."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


def hybrid_search(
    session: Session,
    client: ClientAPI,
    embedder: Embedder,
    document_id: str,
    query: str,
    *,
    semantic_k: int = 8,
    keyword_k: int = 8,
    final_k: int = 6,
) -> list[SearchHit]:
    """Top passages of one document for ``query``; ``score`` is the fused RRF score."""
    semantic = search_semantic(session, client, embedder, document_id, query, semantic_k)
    keyword = search_keyword(session, document_id, query, keyword_k)
    by_id = {hit.chunk_id: hit for hit in [*keyword, *semantic]}
    fused = reciprocal_rank_fusion([[h.chunk_id for h in semantic], [h.chunk_id for h in keyword]])[
        :final_k
    ]
    results = []
    for rank, (chunk_id, score) in enumerate(fused, start=1):
        hit = by_id[chunk_id]
        hit.rank, hit.score = rank, score
        results.append(hit)
    return results
