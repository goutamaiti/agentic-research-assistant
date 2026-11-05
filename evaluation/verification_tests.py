"""Verification evaluation on labelled claim/quote pairs (spec §18.4).

Usage (from backend/, with an LLM key in backend/.env):

    .venv/Scripts/python ../evaluation/verification_tests.py <claims.json>

Reports accuracy, precision/recall for "supported", a confusion matrix, the false
acceptance rate (unsupported claims marked verified — the key safety metric) and the false
rejection rate. Claims still ``pending`` (LLM failure) are counted separately.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.agents.verification_agent import VerificationAgent  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.schemas.evidence import Claim, EvidenceRecord, QuoteMatch  # noqa: E402
from app.schemas.extraction import ExtractionResult, ProcessingMetadata  # noqa: E402
from app.services.llm_service import LLMService, build_transport  # noqa: E402


def main() -> None:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    settings = get_settings()
    transport = build_transport(settings)
    if transport is None:
        raise SystemExit("No LLM API key configured in backend/.env.")
    llm = LLMService(transport, model_id=settings.llm_model_id,
                     max_retries=settings.llm_max_retries)

    claims, evidence = [], []
    for index, pair in enumerate(data["pairs"], start=1):
        cid, eid = f"CLM_{index:03d}", f"EVD_{index:03d}"
        claims.append(Claim(claim_id=cid, category="methodology", claim_text=pair["claim"],
                            origin="directly_extracted", evidence_ids=[eid],
                            field_path="research_analysis.methodology.overall_approach"))
        evidence.append(EvidenceRecord(evidence_id=eid, claim_id=cid, source_text=pair["quote"],
                                       quote_match=QuoteMatch.EXACT, pdf_page_index=0))
    result = ExtractionResult(
        claims=claims, evidence_registry=evidence,
        processing_metadata=ProcessingMetadata(document_id="0" * 32, model_id=llm.model_id,
                                               prompt_version="eval",
                                               processing_status="completed"),
    )
    verified = VerificationAgent(llm).verify(result)

    rows = []
    for pair, claim in zip(data["pairs"], verified.claims, strict=True):
        status = claim.verification_status.value
        predicted = ("pending" if status == "pending"
                     else "supported" if status == "verified" else "unsupported")
        rows.append((pair["gold"], predicted, status))

    judged = [r for r in rows if r[1] != "pending"]
    tp = sum(g == p == "supported" for g, p, _ in judged)
    tn = sum(g == p == "unsupported" for g, p, _ in judged)
    fp = sum(g == "unsupported" and p == "supported" for g, p, _ in judged)
    fn = sum(g == "supported" and p == "unsupported" for g, p, _ in judged)
    n_unsup = tn + fp
    n_sup = tp + fn
    print(f"Pairs: {len(rows)} | judged: {len(judged)} | pending: {len(rows) - len(judged)}")
    print(f"Labels: {data.get('label_status', 'unknown')}")
    if judged:
        print(f"Accuracy: {(tp + tn) / len(judged):.3f}")
        print(f"Precision (supported): {tp / (tp + fp) if tp + fp else 0:.3f}  "
              f"Recall (supported): {tp / n_sup if n_sup else 0:.3f}")
        print(f"False acceptance rate: {fp / n_unsup if n_unsup else 0:.3f} ({fp}/{n_unsup})")
        print(f"False rejection rate: {fn / n_sup if n_sup else 0:.3f} ({fn}/{n_sup})")
        print(f"Confusion (gold x predicted): TP={tp} FN={fn} FP={fp} TN={tn}")
    for gold, _, status in rows:
        print(f"  gold={gold:11s} system={status}")


if __name__ == "__main__":
    main()
