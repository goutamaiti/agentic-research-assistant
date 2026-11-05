from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from app.document_processing.metadata import extract_metadata
from app.document_processing.pdf_parser import find_boilerplate_lines, parse_pdf
from app.document_processing.section_detector import (
    FRONT_MATTER,
    DocumentStructure,
    classify_section,
    detect_structure,
)
from app.document_processing.types import ParsedDocument
from app.schemas.paper import DocumentMetadata, ExtractionStatus
from tests.pdf_factory import ABSTRACT, DOI, KEYWORDS, TITLE, write_paper, write_plain_pdf

BODY_SENTENCE = (
    "This paragraph is ordinary body text that discusses retrieval and evaluation in some "
    "detail so that the parser sees a realistic amount of running English prose."
)


def _analyse(path: Path) -> tuple[ParsedDocument, DocumentStructure, DocumentMetadata]:
    document = parse_pdf(path, ocr_engine=None)
    boilerplate = find_boilerplate_lines(document.pages)
    structure = detect_structure(document, boilerplate)
    return document, structure, extract_metadata(document, structure, boilerplate)


def _set_metadata(path: Path, metadata: dict[str, str]) -> Path:
    out = path.with_name(path.stem + "_meta.pdf")
    with pymupdf.open(path) as doc:
        doc.set_metadata(metadata)
        doc.save(out)
    return out


def _assert_fields_consistent(metadata: DocumentMetadata) -> None:
    for name in DocumentMetadata.model_fields:
        if name == "method":
            continue
        field = getattr(metadata, name)
        assert isinstance(field.status, ExtractionStatus), name
        if field.status is ExtractionStatus.NOT_FOUND:
            assert field.value is None, name
        if field.status is ExtractionStatus.EXTRACTED:
            assert field.value is not None, name
            assert field.source is not None, name


def test_paper_sections_titles_levels_and_types(tmp_path: Path) -> None:
    _, structure, _ = _analyse(write_paper(tmp_path / "paper.pdf"))
    got = [(s.title, s.level, s.section_type) for s in structure.sections]
    assert got == [
        ("Front matter", 1, FRONT_MATTER),
        ("Abstract", 1, "abstract"),
        ("Introduction", 1, "introduction"),
        ("Related Work", 1, "related_work"),
        ("Methodology", 1, "methodology"),
        ("Data Preprocessing", 2, "methodology"),
        ("Experiments", 1, "experiments"),
        ("Results", 1, "results"),
        ("Conclusion", 1, "conclusion"),
        ("References", 1, "references"),
    ]
    assert [s.section_index for s in structure.sections] == list(range(len(got)))


def test_paper_section_hierarchy_and_pages(tmp_path: Path) -> None:
    _, structure, _ = _analyse(write_paper(tmp_path / "paper.pdf"))
    sections = structure.sections
    by_title = {s.title: s for s in sections}

    front = sections[0]
    assert front.section_index == 0 and front.parent_index is None
    assert front.start_page_index == 0
    # The title belongs to the front matter, not to a section.
    front_text = " ".join(p.text for p in structure.paragraphs if p.section_index == 0)
    assert "Hybrid Retrieval" in front_text

    sub = by_title["Data Preprocessing"]
    assert sub.parent_index == by_title["Methodology"].section_index
    assert all(s.parent_index is None for s in sections if s.level == 1)

    assert by_title["Methodology"].start_page_index == 1
    assert by_title["References"].start_page_index == 2
    starts = [s.start_page_index for s in sections]
    assert starts == sorted(starts)
    for section in sections:
        assert section.start_page_index <= section.end_page_index
        if section.parent_index is not None:
            assert sections[section.parent_index].end_page_index >= section.end_page_index

    # Paragraph provenance: every paragraph sits in a known section on a real page,
    # and running headers / page numbers never become paragraphs.
    for paragraph in structure.paragraphs:
        section = sections[paragraph.section_index]
        assert section.start_page_index <= paragraph.pdf_page_index <= section.end_page_index
        assert "Synthetic Journal of Retrieval Testing" not in paragraph.text
        assert paragraph.text.strip() not in {"101", "102", "103"}
    refs = [
        p for p in structure.paragraphs if p.section_index == by_title["References"].section_index
    ]
    assert refs and refs[0].text.startswith("[1]")


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Abstract", "abstract"),
        ("Introduction", "introduction"),
        ("Background", "related_work"),
        ("Related Work", "related_work"),
        ("Proposed Approach", "methodology"),
        ("Materials and Methods", "methodology"),
        ("Experimental Setup", "experiments"),
        ("Evaluation", "experiments"),
        ("Results", "results"),
        ("Discussion", "discussion"),
        ("Limitations", "limitations"),
        ("Future Work", "future_work"),
        ("Conclusions", "conclusion"),
        ("Acknowledgements", "acknowledgments"),
        ("References", "references"),
        ("Bibliography", "references"),
        ("Appendix A", "appendix"),
        ("Ethics Statement", "other"),
    ],
)
def test_classify_section(title: str, expected: str) -> None:
    assert classify_section(title) == expected


def test_numbered_body_sentence_is_not_a_heading(tmp_path: Path) -> None:
    sentence = "1 We propose a method that improves retrieval for grounded answers."
    path = write_plain_pdf(tmp_path / "plain.pdf", [sentence, BODY_SENTENCE])
    _, structure, _ = _analyse(path)
    assert [s.section_type for s in structure.sections] == [FRONT_MATTER]
    assert structure.paragraphs[0].text == sentence
    assert all(p.section_index == 0 for p in structure.paragraphs)


def test_inline_abstract_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "inline.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_textbox(
        pymupdf.Rect(60, 70, 535, 110), "A Short Inline Paper", fontsize=18, fontname="hebo"
    )
    # Base-14 fonts cannot encode an em dash; the HTML box embeds a Unicode font.
    page.insert_htmlbox(
        pymupdf.Rect(60, 130, 535, 200),
        "Abstract—We describe an inline abstract that shares a line with its label.",
        css="* {font-family: sans-serif; font-size: 10px;}",
    )
    page.insert_textbox(pymupdf.Rect(60, 230, 535, 300), BODY_SENTENCE, fontsize=10)
    doc.save(path)
    doc.close()

    _, structure, metadata = _analyse(path)
    abstract = next(s for s in structure.sections if s.section_type == "abstract")
    assert abstract.title == "Abstract" and abstract.level == 1
    first = next(p for p in structure.paragraphs if p.section_index == abstract.section_index)
    assert first.text.startswith("We describe an inline abstract")
    assert metadata.abstract.status is ExtractionStatus.EXTRACTED
    assert metadata.abstract.value is not None
    assert metadata.abstract.value.startswith("We describe an inline abstract")
    assert "Abstract" not in metadata.abstract.value


def test_paper_metadata_fields(tmp_path: Path) -> None:
    _, _, metadata = _analyse(write_paper(tmp_path / "paper.pdf"))
    _assert_fields_consistent(metadata)
    assert metadata.method == "deterministic"

    assert metadata.title.value == TITLE
    assert metadata.title.status is ExtractionStatus.EXTRACTED
    assert metadata.title.source == "first_page_layout"
    assert metadata.title.pdf_page_index == 0

    assert metadata.doi.value == DOI
    assert metadata.doi.source == "text_pattern"
    assert metadata.doi.pdf_page_index == 0

    assert metadata.publication_year.value == 2024
    assert metadata.publication_year.pdf_page_index == 0
    assert metadata.publication_year.evidence_text is not None
    assert "2024" in metadata.publication_year.evidence_text

    assert metadata.keywords.value == [
        "retrieval augmented generation",
        "BM25",
        "dense embeddings",
        "citations",
    ]
    assert metadata.keywords.evidence_text == KEYWORDS

    assert metadata.abstract.value == ABSTRACT
    assert metadata.abstract.source == "section_text"
    assert "Keywords" not in metadata.abstract.value

    assert metadata.document_language.value == "en"
    assert metadata.document_language.status is ExtractionStatus.EXTRACTED

    # Never guessed: authors and venue stay not_found with an explanation.
    assert metadata.authors.status is ExtractionStatus.NOT_FOUND
    assert metadata.authors.value is None and metadata.authors.note
    assert metadata.journal_or_conference.status is ExtractionStatus.NOT_FOUND
    assert metadata.journal_or_conference.value is None


def test_missing_doi_keywords_and_year_are_not_found(tmp_path: Path) -> None:
    path = write_paper(tmp_path / "bare.pdf", with_doi=False, with_keywords=False)
    _, _, metadata = _analyse(path)
    _assert_fields_consistent(metadata)
    for field in (metadata.doi, metadata.keywords, metadata.publication_year):
        assert field.status is ExtractionStatus.NOT_FOUND
        assert field.value is None
        assert field.pdf_page_index is None and field.evidence_text is None
    assert metadata.publication_year.note
    # The rest of the paper is still read.
    assert metadata.title.value == TITLE
    assert metadata.abstract.value == ABSTRACT


def test_authors_from_pdf_metadata(tmp_path: Path) -> None:
    path = write_paper(tmp_path / "authors.pdf", metadata={"author": "A. One; B. Two"})
    _, _, metadata = _analyse(path)
    assert metadata.authors.status is ExtractionStatus.EXTRACTED
    assert metadata.authors.value == ["A. One", "B. Two"]
    assert metadata.authors.source == "pdf_metadata"
    assert metadata.authors.evidence_text == "A. One; B. Two"
    assert metadata.authors.note


def test_bad_pdf_metadata_title_is_ignored(tmp_path: Path) -> None:
    plain = write_plain_pdf(tmp_path / "plain.pdf", [BODY_SENTENCE, BODY_SENTENCE])
    path = _set_metadata(plain, {"title": "Microsoft Word - draft.docx"})
    document, _, metadata = _analyse(path)
    assert document.pdf_metadata.get("title") == "Microsoft Word - draft.docx"
    assert metadata.title.status is ExtractionStatus.NOT_FOUND
    assert metadata.title.value is None and metadata.title.source is None
    _assert_fields_consistent(metadata)


def test_good_pdf_metadata_title_used_when_no_layout_title(tmp_path: Path) -> None:
    plain = write_plain_pdf(tmp_path / "plain.pdf", [BODY_SENTENCE, BODY_SENTENCE])
    path = _set_metadata(plain, {"title": "Grounded Answers from Single Papers"})
    _, _, metadata = _analyse(path)
    assert metadata.title.value == "Grounded Answers from Single Papers"
    assert metadata.title.source == "pdf_metadata"
    assert metadata.title.pdf_page_index is None
    assert metadata.title.note


def test_plain_pdf_has_no_abstract_or_title(tmp_path: Path) -> None:
    _, _, metadata = _analyse(write_plain_pdf(tmp_path / "plain.pdf", [BODY_SENTENCE]))
    _assert_fields_consistent(metadata)
    assert metadata.title.status is ExtractionStatus.NOT_FOUND
    assert metadata.abstract.status is ExtractionStatus.NOT_FOUND
    # Too little text to decide: language is not guessed.
    assert metadata.document_language.value is None
    assert metadata.document_language.note
