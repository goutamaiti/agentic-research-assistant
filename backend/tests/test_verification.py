"""Claim verification (Amendment A1 step 5): deterministic rules and LLM judgement."""

from __future__ import annotations

from pathlib import Path

from app.agents.verification_agent import VerificationAgent
from app.schemas.evidence import Claim, EvidenceRecord, QuoteMatch
from app.schemas.extraction import ExtractionResult, ProcessingMetadata
from app.services.llm_service import LLMError, LLMService
from tests.conftest import make_client, make_settings
from tests.fakes import FakeLLMTransport, grounded_responder
from tests.pdf_factory import write_paper


def _result(*claims: tuple[str, str, list[tuple[str, QuoteMatch]]]) -> ExtractionResult:
    claim_rows, evidence_rows = [], []
    for index, (category, text, quotes) in enumerate(claims, start=1):
        cid = f"CLM_{index:03d}"
        ids = []
        for quote, match in quotes:
            eid = f"EVD_{len(evidence_rows) + 1:03d}"
            ids.append(eid)
            located = match != QuoteMatch.NOT_FOUND
            evidence_rows.append(
                EvidenceRecord(
                    evidence_id=eid,
                    claim_id=cid,
                    source_text=quote,
                    quote_match=match,
                    pdf_page_index=0 if located else None,
                )
            )
        claim_rows.append(
            Claim(
                claim_id=cid,
                category=category,
                claim_text=text,
                origin="directly_extracted",
                evidence_ids=ids,
                field_path="paper_metadata.title"
                if category == "paper_metadata"
                else "research_analysis.results.items[0]",
            )
        )
    return ExtractionResult(
        claims=claim_rows,
        evidence_registry=evidence_rows,
        processing_metadata=ProcessingMetadata(
            document_id="a" * 32, model_id="m", prompt_version="p", processing_status="completed"
        ),
    )


def _llm(status: str = "verified") -> LLMService:
    import re

    def responder(task, prompt, schema):
        ids = re.findall(r"^CLAIM (CLM_\d+):", prompt, re.MULTILINE)
        return {"verdicts": [{"claim_id": i, "status": status, "explanation": "x"} for i in ids]}

    return LLMService(FakeLLMTransport(responder), model_id="m", sleep=lambda s: None)


def _statuses(result: ExtractionResult) -> list[str]:
    return [c.verification_status.value for c in result.claims]


def test_deterministic_rules() -> None:
    result = _result(
        ("result", "No evidence here.", []),
        ("result", "Fabricated support.", [("not in the paper at all", QuoteMatch.NOT_FOUND)]),
        (
            "paper_metadata",
            "title: Attention Is All You Need",
            [("Attention Is All You Need", QuoteMatch.EXACT)],
        ),
    )
    verified = VerificationAgent(None).verify(result)
    assert _statuses(verified) == ["not_verifiable", "unsupported", "verified"]
    assert verified.evidence_registry[0].verification_status == "unsupported"


def test_llm_verdict_is_used_and_number_mismatch_downgrades() -> None:
    result = _result(
        (
            "result",
            "BLEU = 28.4: the model scores 28.4 BLEU.",
            [("achieves 28.4 BLEU on the task", QuoteMatch.EXACT)],
        ),
        (
            "result",
            "BLEU = 41.0: the big model scores 41.0 BLEU.",
            [("the big model performs best", QuoteMatch.EXACT)],
        ),
    )
    verified = VerificationAgent(_llm("verified")).verify(result)
    assert _statuses(verified) == ["verified", "partially_supported"]
    assert "41.0" in verified.claims[1].verification_explanation


def test_contradicted_verdict_kept() -> None:
    result = _result(("result", "Accuracy fell.", [("accuracy rose sharply", QuoteMatch.EXACT)]))
    assert _statuses(VerificationAgent(_llm("contradicted")).verify(result)) == ["contradicted"]


def test_without_llm_or_on_failure_claims_stay_pending_never_verified() -> None:
    claim = ("result", "The model is fast.", [("the model is fast", QuoteMatch.EXACT)])
    assert _statuses(VerificationAgent(None).verify(_result(claim))) == ["pending"]

    def broken(task, prompt, schema):
        raise LLMError("provider_error", "down", retryable=False)

    failing = LLMService(FakeLLMTransport(broken), model_id="m", sleep=lambda s: None)
    result = VerificationAgent(failing).verify(_result(claim))
    assert _statuses(result) == ["pending"]
    assert any("Verification batch failed" in w for w in result.processing_metadata.warnings)


def test_evidence_endpoint_lists_claims_with_passages(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    llm = LLMService(FakeLLMTransport(grounded_responder), model_id="m", sleep=lambda s: None)
    with make_client(settings, llm_service=llm) as client:
        pdf = write_paper(tmp_path / "p.pdf")
        document_id = client.post(
            "/api/documents/upload", files={"file": ("p.pdf", pdf.read_bytes())}
        ).json()["id"]
        client.post(f"/api/documents/{document_id}/analyze")
        stages = {
            s["stage"]: s
            for s in client.get(f"/api/documents/{document_id}/status").json()["stages"]
        }
        body = client.get(f"/api/documents/{document_id}/evidence").json()
    assert stages["evidence_verification"]["status"] == "completed"
    assert sum(body["verification_summary"].values()) == len(body["claims"])
    for claim in body["claims"]:
        assert claim["verification_status"] != "pending"
        assert [e["evidence_id"] for e in claim["evidence"]] == claim["evidence_ids"]
        if claim["verification_status"] == "verified":
            assert any(e["quote_match"] != "not_found" for e in claim["evidence"])
