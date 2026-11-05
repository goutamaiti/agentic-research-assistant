"""Retrieval evaluation: semantic vs hybrid (RRF) with Precision@K, Recall@K and MRR (spec §18.2).

Usage (from backend/, after the paper has been uploaded and analysed in that storage):

    .venv/Scripts/python ../evaluation/retrieval_tests.py <ground_truth.json> [storage_dir]

Relevance is judged at section level from the ground-truth file. Results are only as
good as the labels: a DRAFT label file must be human-reviewed before reporting numbers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import Settings  # noqa: E402
from app.database.connection import create_db_engine, create_session_factory  # noqa: E402
from app.database.models import Document  # noqa: E402
from app.retrieval.embeddings import SentenceTransformerEmbedder  # noqa: E402
from app.retrieval.hybrid_search import hybrid_search  # noqa: E402
from app.retrieval.vector_store import create_chroma_client  # noqa: E402
from app.services.retrieval_service import search_keyword, search_semantic  # noqa: E402

K = 5


def metrics(ranked_sections: list[list[str]], relevant: list[set[str]], total_relevant: list[int]):
    p_at_k, r_at_k, rr = [], [], []
    for sections, rel, n_rel in zip(ranked_sections, relevant, total_relevant, strict=True):
        hits = [s in rel for s in sections[:K]]
        p_at_k.append(sum(hits) / K)
        r_at_k.append(sum(hits) / n_rel if n_rel else 0.0)
        first = next((i for i, h in enumerate(hits, start=1) if h), None)
        rr.append(1.0 / first if first else 0.0)
    n = len(rr)
    return {f"P@{K}": sum(p_at_k) / n, f"R@{K}": sum(r_at_k) / n, "MRR": sum(rr) / n}


def main() -> None:
    truth = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    overrides = {"storage_dir": sys.argv[2]} if len(sys.argv) > 2 else {}
    settings = Settings(log_level="WARNING", **overrides)
    factory = create_session_factory(create_db_engine(settings.sqlalchemy_url))
    chroma = create_chroma_client(settings.chroma_path)
    embedder = SentenceTransformerEmbedder(settings.embedding_model)

    with factory() as session:
        document = session.query(Document).filter(Document.title == truth["title"]).first()
        if document is None:
            raise SystemExit(f"Paper {truth['title']!r} is not in this storage; analyse it first.")
        from app.database.models import DocumentChunk

        chunks = session.query(DocumentChunk).filter_by(document_id=document.id, indexed=True)
        counts: dict[str, int] = {}
        for chunk in chunks:
            counts[chunk.section_name] = counts.get(chunk.section_name, 0) + 1

        runs = {"semantic": [], "keyword (BM25)": [], "hybrid (RRF)": []}
        relevant, totals = [], []
        for item in truth["retrieval_queries"]:
            rel = set(item["relevant_sections"])
            relevant.append(rel)
            totals.append(min(K, sum(counts.get(s, 0) for s in rel)))
            q = item["query"]
            runs["semantic"].append([h.section_name for h in
                                     search_semantic(session, chroma, embedder, document.id, q, K)])
            runs["keyword (BM25)"].append([h.section_name for h in
                                           search_keyword(session, document.id, q, K)])
            runs["hybrid (RRF)"].append([h.section_name for h in hybrid_search(
                session, chroma, embedder, document.id, q, semantic_k=8, keyword_k=8,
                final_k=K)])

    print(f"Paper: {truth['title']} | queries: {len(relevant)} | K={K}")
    print(f"Labels: {truth.get('label_status', 'unknown')}")
    for name, ranked in runs.items():
        scores = metrics(ranked, relevant, totals)
        print(f"  {name:15s} " + "  ".join(f"{k}={v:.3f}" for k, v in scores.items()))


if __name__ == "__main__":
    main()
