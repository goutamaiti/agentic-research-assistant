"""Evidence linking (quote -> exact source span -> PDF page) and the extraction schemas."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.schemas import extraction as ex
from app.schemas.evidence import (
    Claim,
    EvidenceRecord,
    Origin,
    QuoteMatch,
    VerificationStatus,
)
from app.schemas.paper import ExtractionStatus
from app.services.evidence_linker import (
    MIN_QUOTE_CHARS,
    EvidenceLinker,
    PassageSource,
    find_span,
    normalise,
    normalise_with_map,
)

# ----- normalise_with_map -------------------------------------------------------------


def test_normalise_expands_ligature_and_maps_both_letters_to_source_char() -> None:
    text, index_map = normalise_with_map("ﬁnal")
    assert text == "final"
    assert index_map == [0, 0, 1, 2, 3]


def test_normalise_maps_smart_quotes_and_dashes_to_ascii() -> None:
    text, index_map = normalise_with_map("“A—B’s” – x−y")
    assert text == '"a-b\'s" - x-y'
    assert len(index_map) == len(text)


def test_normalise_drops_soft_hyphen_and_keeps_original_indices() -> None:
    source = "com­pute"
    text, index_map = normalise_with_map(source)
    assert text == "compute"
    assert index_map == [0, 1, 2, 4, 5, 6, 7]
    assert "".join(source[i] for i in index_map) == "compute"


def test_normalise_collapses_whitespace_and_nbsp_and_trims_edges() -> None:
    source = "  Deep   Learning\n\tworks  "
    text, index_map = normalise_with_map(source)
    assert text == "deep learning works"
    assert len(index_map) == len(text)
    # First output char comes from 'D' at index 2; single collapsed space from index 6.
    assert index_map[0] == 2
    assert index_map[4] == 6
    assert source[index_map[5]] == "L"
    assert source[index_map[-1]] == "s"


def test_normalise_lowercases() -> None:
    assert normalise("BLEU Score") == "bleu score"


# ----- find_span ----------------------------------------------------------------------

HAYSTACK = (
    "We propose a ﬁne-tuned Transformer. The model achieves a “state–of–the"
    "–art” BLEU   score of 28.4 on WMT14."
)


def test_find_span_exact() -> None:
    found = find_span(HAYSTACK, "We propose a")
    assert found == ("We propose a", QuoteMatch.EXACT)


def test_find_span_exact_ignores_surrounding_whitespace_in_quote() -> None:
    assert find_span(HAYSTACK, "  BLEU   score of 28.4  ") == (
        "BLEU   score of 28.4",
        QuoteMatch.EXACT,
    )


def test_find_span_normalized_returns_original_source_span_not_quote() -> None:
    quote = 'achieves a "state-of-the-art" bleu score'
    found = find_span(HAYSTACK, quote)
    assert found is not None
    span, match = found
    assert match is QuoteMatch.NORMALIZED
    assert span == "achieves a “state–of–the–art” BLEU   score"
    assert span != quote
    assert span in HAYSTACK


def test_find_span_normalized_through_ligature() -> None:
    found = find_span(HAYSTACK, "a fine-tuned transformer")
    assert found == ("a ﬁne-tuned Transformer", QuoteMatch.NORMALIZED)


def test_find_span_trims_edge_punctuation() -> None:
    found = find_span(HAYSTACK, "(BLEU score of 28.4 on WMT14).…")
    assert found is not None
    span, match = found
    assert match is QuoteMatch.NORMALIZED
    assert span == "BLEU   score of 28.4 on WMT14"


def test_find_span_rejects_too_short_quote_even_when_exact() -> None:
    short = "We prop"
    assert len(short) < MIN_QUOTE_CHARS
    assert short in HAYSTACK
    assert find_span(HAYSTACK, short) is None
    assert find_span(HAYSTACK, "   28.4   ") is None


def test_find_span_accepts_quote_at_minimum_length() -> None:
    quote = "We propo"
    assert len(quote) == MIN_QUOTE_CHARS
    assert find_span(HAYSTACK, quote) == (quote, QuoteMatch.EXACT)


def test_find_span_rejects_quote_that_is_short_after_trimming_punctuation() -> None:
    # Long enough as given, but the only matchable part is shorter than the minimum.
    assert find_span("value is 28.4 here", '"(28.4)"...') is None


def test_find_span_rejects_paraphrase() -> None:
    assert find_span(HAYSTACK, "The model obtains a BLEU score of 28.4 on WMT14") is None
    assert find_span(HAYSTACK, "We propose a fine-tuned Transformer model") is None


# ----- EvidenceLinker -----------------------------------------------------------------

PAGE_0 = "Introduction. Neural machine translation has improved rapidly."
PAGE_1 = "Our encoder uses eight attention heads per layer."
PAGE_2 = "Training ran for three days on eight GPUs."


def _linker() -> EvidenceLinker:
    passages = [
        PassageSource("P01", "chunk-a", PAGE_0, "Introduction", 0, 0),
        PassageSource("P02", "chunk-b", PAGE_1 + "\n" + PAGE_2, "Method", 1, 2),
    ]
    return EvidenceLinker(
        passages,
        page_texts={0: PAGE_0, 1: PAGE_1, 2: PAGE_2},
        displayed_pages={0: "101", 1: "102", 2: None},
    )


def test_resolve_cited_passage_hit_gives_full_location() -> None:
    result = _linker().resolve("P01", "Neural machine translation has improved")
    assert result.quote_match is QuoteMatch.EXACT
    assert result.source_text == "Neural machine translation has improved"
    assert result.chunk_id == "chunk-a"
    assert result.pdf_page_index == 0
    assert result.displayed_page_number == "101"
    assert result.section_name == "Introduction"
    assert result.corrected_passage is False


def test_resolve_strips_whitespace_around_passage_id() -> None:
    result = _linker().resolve(" P01 ", "Neural machine translation")
    assert result.chunk_id == "chunk-a"
    assert result.corrected_passage is False


def test_resolve_multi_page_chunk_uses_page_containing_quote() -> None:
    linker = _linker()
    first = linker.resolve("P02", "eight attention heads")
    assert first.pdf_page_index == 1
    assert first.displayed_page_number == "102"
    second = linker.resolve("P02", "three days on eight GPUs")
    assert second.pdf_page_index == 2
    assert second.displayed_page_number is None  # no printed label for that page
    assert second.chunk_id == "chunk-b"
    assert second.section_name == "Method"


def test_resolve_normalized_quote_in_multi_page_chunk_finds_page() -> None:
    result = _linker().resolve("P02", "TRAINING  RAN for three days")
    assert result.quote_match is QuoteMatch.NORMALIZED
    assert result.source_text == "Training ran for three days"
    assert result.pdf_page_index == 2


def test_resolve_quote_spanning_page_break_cites_start_page() -> None:
    result = _linker().resolve("P02", "heads per layer. Training ran")
    assert result.quote_match is QuoteMatch.NORMALIZED  # "\n" vs " " in the source
    assert result.source_text == "heads per layer.\nTraining ran"
    assert result.pdf_page_index == 1
    assert result.displayed_page_number == "102"


def test_resolve_unknown_passage_id_corrected_to_passage_with_quote() -> None:
    result = _linker().resolve("P99", "three days on eight GPUs")
    assert result.corrected_passage is True
    assert result.quote_match is QuoteMatch.EXACT
    assert result.chunk_id == "chunk-b"
    assert result.pdf_page_index == 2
    assert result.section_name == "Method"


def test_resolve_wrong_existing_passage_id_is_corrected() -> None:
    result = _linker().resolve("P02", "Neural machine translation")
    assert result.corrected_passage is True
    assert result.chunk_id == "chunk-a"
    assert result.pdf_page_index == 0
    assert result.displayed_page_number == "101"
    assert result.section_name == "Introduction"


def test_resolve_fabricated_quote_has_no_location() -> None:
    result = _linker().resolve("P01", "Our   method  beats all\nbaselines by 40%")
    assert result.quote_match is QuoteMatch.NOT_FOUND
    assert result.source_text == "Our method beats all baselines by 40%"
    assert result.pdf_page_index is None
    assert result.displayed_page_number is None
    assert result.section_name is None
    assert result.chunk_id is None
    assert result.corrected_passage is False


def test_resolve_too_short_quote_is_not_found() -> None:
    result = _linker().resolve("P01", "Neural")
    assert result.quote_match is QuoteMatch.NOT_FOUND
    assert result.pdf_page_index is None


# ----- llm_json_schema ----------------------------------------------------------------

RESPONSE_MODELS: list[type[BaseModel]] = [
    ex.OverviewResponse,
    ex.MethodsResponse,
    ex.ExperimentsResponse,
    ex.OutlookResponse,
    ex.TerminologyResponse,
    ex.MetadataResponse,
]


def _walk(node: Any, keys: list[str], property_names: list[str], required: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            keys.append(key)
            if key == "properties":
                property_names.extend(value)
                for prop in value.values():
                    _walk(prop, keys, property_names, required)
            elif key == "required":
                required.extend(value)
            else:
                _walk(value, keys, property_names, required)
    elif isinstance(node, list):
        for item in node:
            _walk(item, keys, property_names, required)


@pytest.mark.parametrize("model", RESPONSE_MODELS, ids=lambda m: m.__name__)
def test_llm_json_schema_is_inlined_untitled_and_hides_app_fields(model: type[BaseModel]) -> None:
    schema = ex.llm_json_schema(model)
    keys: list[str] = []
    property_names: list[str] = []
    required: list[str] = []
    _walk(schema, keys, property_names, required)
    assert "$ref" not in keys
    assert "$defs" not in keys
    assert "title" not in keys
    assert property_names, "schema should describe properties"
    assert not set(property_names) & ex.APP_OWNED_FIELDS
    assert not set(required) & ex.APP_OWNED_FIELDS
    # The top-level fields are still all present.
    assert set(schema["properties"]) == set(model.model_fields) - ex.APP_OWNED_FIELDS


def test_llm_json_schema_keeps_support_and_status_for_items() -> None:
    schema = ex.llm_json_schema(ex.MetadataResponse)
    venue = schema["properties"]["journal_or_conference"]
    assert set(venue["properties"]) == {"support", "value", "status"}
    quote_ref = venue["properties"]["support"]["items"]
    assert set(quote_ref["properties"]) == {"passage_id", "quote"}
    assert venue["additionalProperties"] is False
    assert "not_found" in venue["properties"]["status"]["enum"]


def test_llm_json_schema_hides_original_abstract_and_task_status() -> None:
    schema = ex.llm_json_schema(ex.OverviewResponse)
    abstract = schema["properties"]["abstract"]["properties"]
    assert "original_abstract" not in abstract
    assert "task_status" not in abstract
    assert {"status", "stated_problem", "approach"} <= set(abstract)


def test_llm_json_schema_does_not_mutate_pydantic_schema() -> None:
    ex.llm_json_schema(ex.OverviewResponse)
    assert "$defs" in ex.OverviewResponse.model_json_schema()


# ----- Claim / EvidenceRecord ---------------------------------------------------------


def _claim(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "claim_id": "CLM_001",
        "category": "objective",
        "claim_text": "The paper aims to improve translation.",
        "origin": "author_claimed",
        "field_path": "research_analysis.objectives.main_objective",
    }
    data.update(overrides)
    return data


def _evidence(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "evidence_id": "EVD_001",
        "claim_id": "CLM_001",
        "source_text": "We aim to improve translation.",
        "quote_match": "exact",
    }
    data.update(overrides)
    return data


def test_claim_defaults() -> None:
    claim = Claim.model_validate(_claim())
    assert claim.origin is Origin.AUTHOR_CLAIMED
    assert claim.extraction_status is ExtractionStatus.EXTRACTED
    assert claim.verification_status is VerificationStatus.PENDING
    assert claim.confidence is None
    assert claim.evidence_ids == []


@pytest.mark.parametrize("bad_id", ["CLM_1", "CLM_01", "clm_001", "CLM_00a", "EVD_001", ""])
def test_claim_rejects_bad_ids(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        Claim.model_validate(_claim(claim_id=bad_id))


def test_claim_accepts_long_ids() -> None:
    assert Claim.model_validate(_claim(claim_id="CLM_12345")).claim_id == "CLM_12345"


@pytest.mark.parametrize(
    "field,value",
    [
        ("origin", "paper"),
        ("category", "novelty"),
        ("extraction_status", "found"),
        ("verification_status", "true"),
    ],
)
def test_claim_rejects_unknown_enum_values(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        Claim.model_validate(_claim(**{field: value}))


def test_claim_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Claim.model_validate(_claim(page=3))


@pytest.mark.parametrize("confidence", [-0.01, 1.01, 2])
def test_claim_rejects_out_of_range_confidence(confidence: float) -> None:
    with pytest.raises(ValidationError):
        Claim.model_validate(_claim(confidence=confidence))


@pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
def test_claim_accepts_confidence_bounds(confidence: float) -> None:
    assert Claim.model_validate(_claim(confidence=confidence)).confidence == confidence


def test_claim_requires_field_path() -> None:
    data = _claim()
    del data["field_path"]
    with pytest.raises(ValidationError):
        Claim.model_validate(data)


def test_evidence_record_defaults_and_valid() -> None:
    record = EvidenceRecord.model_validate(_evidence())
    assert record.quote_match is QuoteMatch.EXACT
    assert record.verification_status is VerificationStatus.PENDING
    assert record.pdf_page_index is None
    assert record.chunk_id is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"evidence_id": "EVD_x"},
        {"evidence_id": "EVD_1"},
        {"evidence_id": "CLM_001"},
        {"claim_id": "CLM_1"},
        {"quote_match": "fuzzy"},
        {"verification_status": "maybe"},
        {"pdf_page_index": -1},
        {"page": 4},
    ],
)
def test_evidence_record_rejects_invalid(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        EvidenceRecord.model_validate(_evidence(**overrides))


# ----- Extraction models --------------------------------------------------------------


def test_grounded_support_is_input_only() -> None:
    field = ex.TextField.model_validate(
        {
            "value": "Improve translation.",
            "status": "extracted",
            "support": [{"passage_id": "P01", "quote": "We aim to improve translation."}],
        }
    )
    assert field.support[0].passage_id == "P01"
    dumped = field.model_dump()
    assert "support" not in dumped
    assert "support" not in field.model_dump(mode="json")
    assert dumped == {
        "claim_ids": [],
        "evidence_ids": [],
        "value": "Improve translation.",
        "status": ExtractionStatus.EXTRACTED,
    }


def test_quote_ref_rejects_empty_and_overlong_quotes() -> None:
    with pytest.raises(ValidationError):
        ex.QuoteRef(passage_id="P01", quote="")
    with pytest.raises(ValidationError):
        ex.QuoteRef(passage_id="P01", quote="x" * 601)


def test_llm_models_reject_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ex.TextField.model_validate({"value": "x", "page": 3})
    with pytest.raises(ValidationError):
        ex.MetadataResponse.model_validate(
            {
                "authors": {},
                "journal_or_conference": {},
                "publication_year": {},
                "keywords": {},
                "doi": {"value": "10.1/x"},
            }
        )


def test_year_field_bounds() -> None:
    with pytest.raises(ValidationError):
        ex.YearField(year=1899)
    with pytest.raises(ValidationError):
        ex.YearField(year=2101)
    assert ex.YearField(year=2017).year == 2017


def _all_categories(result: ex.ExtractionResult) -> list[ex.CategoryBase]:
    sections = [result.research_analysis, result.technical_analysis]
    return [getattr(section, name) for section in sections for name in type(section).model_fields]


def test_category_defaults_are_not_found_and_not_run() -> None:
    result = ex.ExtractionResult(
        processing_metadata=ex.ProcessingMetadata(
            document_id="doc", model_id="m", prompt_version="v1", processing_status="failed"
        )
    )
    categories = _all_categories(result)
    assert len(categories) == 14
    for category in categories:
        assert isinstance(category, ex.CategoryBase)
        assert category.status is ExtractionStatus.NOT_FOUND
        assert category.task_status == "not_run"
    assert result.research_analysis.abstract.original_abstract.status is ExtractionStatus.NOT_FOUND
    assert result.paper_metadata.title.status is ExtractionStatus.NOT_FOUND
    assert result.paper_metadata.title.value is None
    assert result.schema_version == ex.SCHEMA_VERSION


def test_category_rejects_unknown_task_status() -> None:
    with pytest.raises(ValidationError):
        ex.Results(task_status="skipped")
    with pytest.raises(ValidationError):
        ex.Results(status="missing")


def test_extraction_result_round_trips_through_json() -> None:
    result = ex.ExtractionResult(
        paper_metadata=ex.PaperMetadata(
            title=ex.MetadataValue(value="Attention", status="extracted", source="deterministic"),
            authors=ex.MetadataValue(
                value=["A. Author", "B. Author"],
                status="extracted",
                source="llm",
                claim_ids=["CLM_002"],
                evidence_ids=["EVD_002"],
            ),
        ),
        research_analysis=ex.ResearchAnalysis(
            objectives=ex.Objectives(
                status="extracted",
                task_status="completed",
                main_objective=ex.TextField(
                    value="Improve translation.",
                    status="extracted",
                    claim_ids=["CLM_001"],
                    evidence_ids=["EVD_001"],
                ),
            ),
            results=ex.Results(
                status="partially_extracted",
                task_status="failed",
                items=[
                    ex.ResultItem(
                        kind="numerical", description="BLEU 28.4", metric="BLEU", value=28.4
                    )
                ],
            ),
        ),
        technical_analysis=ex.TechnicalAnalysis(
            technical_terminology=ex.TechnicalTerminology(
                task_status="completed",
                terms=[ex.Term(term="Transformer", definition_origin="general_explanation")],
            )
        ),
        claims=[Claim.model_validate(_claim())],
        evidence_registry=[
            EvidenceRecord.model_validate(
                _evidence(pdf_page_index=0, displayed_page_number="1", chunk_id="c1")
            )
        ],
        processing_metadata=ex.ProcessingMetadata(
            document_id="doc",
            workflow_run_id="run",
            model_id="fake-model",
            prompt_version="v1",
            processing_status="partial",
            verification_summary={"pending": 1},
            tasks=[ex.TaskRecord(task="overview", task_status="completed", attempts=1)],
            warnings=["results: failed"],
        ),
    )
    dumped = result.model_dump(mode="json")
    restored = ex.ExtractionResult.model_validate(dumped)
    assert restored == result
    assert restored.model_dump(mode="json") == dumped
    assert dumped["research_analysis"]["results"]["task_status"] == "failed"
    assert dumped["claims"][0]["origin"] == "author_claimed"
    assert dumped["evidence_registry"][0]["quote_match"] == "exact"


def test_extraction_result_requires_processing_metadata() -> None:
    with pytest.raises(ValidationError):
        ex.ExtractionResult.model_validate({})


# ----- statement() --------------------------------------------------------------------


def test_text_field_statement() -> None:
    assert ex.TextField(value="x").statement() == "x"
    assert ex.TextField().statement() is None


def test_result_item_statement() -> None:
    item = ex.ResultItem(kind="numerical", description="BLEU of 28.4 on WMT14", value=28.4)
    assert item.statement() == "BLEU of 28.4 on WMT14"


def test_parameter_statement() -> None:
    assert ex.Parameter(name="lr", value="0.001").statement() == "lr = 0.001"
    assert (
        ex.Parameter(name="dropout", value="0.1", unit="ratio", applies_to="base").statement()
        == "dropout = 0.1 ratio (base)"
    )


def test_algorithm_model_statement() -> None:
    assert ex.AlgorithmModel(name="LSTM").statement() == "The paper uses LSTM."
    assert (
        ex.AlgorithmModel(name="LSTM", category="RNN", role="encoder").statement()
        == "The paper uses LSTM (encoder)."
    )
    assert (
        ex.AlgorithmModel(name="LSTM", category="RNN", purpose="encode").statement()
        == "The paper uses LSTM (encode)."
    )
    rnn = ex.AlgorithmModel(name="LSTM", category="RNN")
    assert rnn.statement() == "The paper uses LSTM (RNN)."


def test_dataset_statement() -> None:
    assert ex.Dataset(name="WMT14").statement() == "Dataset: WMT14"
    assert (
        ex.Dataset(name="WMT14", source="ACL", size="4.5M", split="90/10").statement()
        == "Dataset: WMT14; source ACL; size 4.5M; split 90/10"
    )
    # characteristics are not part of the statement
    assert ex.Dataset(name="X", characteristics="noisy").statement() == "Dataset: X"


def test_term_statement() -> None:
    assert ex.Term(term="Transformer").statement() == "Transformer"
    assert (
        ex.Term(term="Byte Pair Encoding", abbreviation="BPE", definition="subwords").statement()
        == "Byte Pair Encoding (BPE): subwords"
    )
    assert ex.Term(term="Attention", definition="weighting").statement() == "Attention: weighting"


def test_metadata_field_statements() -> None:
    assert ex.AuthorsField(names=["A", "B"]).statement() == "Authors: A, B"
    assert ex.AuthorsField().statement() is None
    assert ex.KeywordsField(keywords=["nlp", "mt"]).statement() == "Keywords: nlp, mt"
    assert ex.KeywordsField().statement() is None
    assert ex.YearField(year=2017).statement() == "Publication year: 2017"
    assert ex.YearField().statement() is None


def test_other_statements() -> None:
    assert (
        ex.PriorApproach(name="RNN", description="sequential models").statement()
        == "RNN: sequential models"
    )
    assert ex.MethodologyStep(step_number=2, operation="Tokenise").statement() == "Step 2: Tokenise"
    with pytest.raises(ValidationError):
        ex.MethodologyStep(step_number=0, operation="x")
    with pytest.raises(NotImplementedError):
        ex.Grounded().statement()
