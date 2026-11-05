from __future__ import annotations

from pathlib import Path

import pytest

from app.database.models import PageExtractionStatus
from app.document_processing.ocr import _lines_from_tesseract
from app.document_processing.pdf_parser import (
    PdfValidationError,
    find_boilerplate_lines,
    has_pdf_header,
    is_boilerplate,
    parse_pdf,
    validate_pdf,
)
from app.document_processing.types import ParsedPage, TextLine, join_lines
from tests.fakes import FakeOcr
from tests.pdf_factory import (
    RUNNING_HEADER,
    write_blank_pdf,
    write_corrupt_pdf,
    write_encrypted_pdf,
    write_mixed_pdf,
    write_paper,
    write_scanned_pdf,
)

# ----- validation ---------------------------------------------------------------------


def test_validate_pdf_ok(tmp_path: Path) -> None:
    info = validate_pdf(write_paper(tmp_path / "paper.pdf"))
    assert info.page_count == 3


@pytest.mark.parametrize(
    ("writer", "code"),
    [
        (lambda p: p.write_bytes(b"hello, this is plain text\n" * 10) and p, "not_pdf"),
        (write_encrypted_pdf, "encrypted_pdf"),
        (write_corrupt_pdf, "corrupt_pdf"),
    ],
)
def test_validate_pdf_rejections(tmp_path: Path, writer, code: str) -> None:
    path = tmp_path / "bad.pdf"
    writer(path)
    with pytest.raises(PdfValidationError) as excinfo:
        validate_pdf(path)
    assert excinfo.value.code == code
    assert excinfo.value.message


def test_has_pdf_header_within_first_1024_bytes() -> None:
    assert has_pdf_header(b"%PDF-1.7\n")
    assert has_pdf_header(b"\x00" * 500 + b"%PDF-1.4")
    assert not has_pdf_header(b"\x00" * 1024 + b"%PDF-1.4")
    assert not has_pdf_header(b"PK\x03\x04 not a pdf")


# ----- page extraction and displayed page numbers -------------------------------------


def test_parse_pdf_pages_extracted_with_footer_page_numbers(tmp_path: Path) -> None:
    doc = parse_pdf(write_paper(tmp_path / "paper.pdf"), ocr_engine=None)
    assert doc.page_count == len(doc.pages) == 3
    assert [p.pdf_page_index for p in doc.pages] == [0, 1, 2]
    assert all(p.extraction_status == PageExtractionStatus.EXTRACTED for p in doc.pages)
    assert not any(p.ocr_used for p in doc.pages)
    assert [p.displayed_page_number for p in doc.pages] == ["101", "102", "103"]
    assert doc.warnings == []
    assert "Abstract" in doc.pages[0].text
    assert "References" in doc.pages[2].text


def test_no_footer_numbers_means_no_displayed_page_numbers(tmp_path: Path) -> None:
    doc = parse_pdf(write_paper(tmp_path / "paper.pdf", footer_start=None), ocr_engine=None)
    assert [p.displayed_page_number for p in doc.pages] == [None, None, None]


def test_pdf_page_labels_used_as_is(tmp_path: Path) -> None:
    labels = [{"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 1}]
    doc = parse_pdf(write_paper(tmp_path / "paper.pdf", page_labels=labels), ocr_engine=None)
    assert [p.pdf_label for p in doc.pages] == ["i", "ii", "iii"]
    assert [p.displayed_page_number for p in doc.pages] == ["i", "ii", "iii"]


# ----- boilerplate --------------------------------------------------------------------


def test_running_header_detected_as_boilerplate(tmp_path: Path) -> None:
    doc = parse_pdf(write_paper(tmp_path / "paper.pdf"), ocr_engine=None)
    boilerplate = find_boilerplate_lines(doc.pages)
    assert RUNNING_HEADER.lower() in boilerplate
    # Footer page numbers normalise to the same pattern and repeat on every page.
    assert "#" in boilerplate
    assert find_boilerplate_lines(doc.pages[:2]) == set()


def test_is_boilerplate_only_in_margin_band() -> None:
    page = ParsedPage(
        pdf_page_index=0,
        width=595,
        height=842,
        blocks=[],
        extraction_status=PageExtractionStatus.EXTRACTED,
    )
    header = TextLine(text=RUNNING_HEADER, size=8, bold=False, y0=22, y1=32)
    footer_num = TextLine(text="- 17 -", size=8, bold=False, y0=810, y1=820)
    roman = TextLine(text="xiv", size=8, bold=False, y0=810, y1=820)
    body_same_text = TextLine(text=RUNNING_HEADER, size=10, bold=False, y0=400, y1=412)
    body_number = TextLine(text="42", size=10, bold=False, y0=400, y1=412)
    other_margin = TextLine(text="Draft notes", size=8, bold=False, y0=22, y1=32)
    boilerplate = {RUNNING_HEADER.lower()}

    assert is_boilerplate(header, page, boilerplate)
    assert is_boilerplate(footer_num, page, boilerplate)
    assert is_boilerplate(roman, page, boilerplate)
    assert not is_boilerplate(body_same_text, page, boilerplate)
    assert not is_boilerplate(body_number, page, boilerplate)
    assert not is_boilerplate(other_margin, page, boilerplate)


# ----- OCR fallback -------------------------------------------------------------------


def test_scanned_page_without_ocr_engine_is_unavailable(tmp_path: Path) -> None:
    doc = parse_pdf(write_scanned_pdf(tmp_path / "scan.pdf"), ocr_engine=None)
    (page,) = doc.pages
    assert page.extraction_status == PageExtractionStatus.OCR_UNAVAILABLE
    assert page.ocr_used is False
    assert page.ocr_confidence is None
    assert page.blocks == []
    assert any("OCR is not available" in w for w in page.warnings)
    assert doc.warnings == ["1 page(s) could not be read: [0]"]


def test_scanned_page_with_fake_ocr_is_ocr_extracted(tmp_path: Path) -> None:
    ocr = FakeOcr()
    doc = parse_pdf(write_scanned_pdf(tmp_path / "scan.pdf", pages=2), ocr_engine=ocr)
    assert ocr.calls == 2
    for page in doc.pages:
        assert page.extraction_status == PageExtractionStatus.OCR_EXTRACTED
        assert page.ocr_used is True
        assert page.ocr_confidence == 91.0
        assert FakeOcr.TEXT[0] in page.text
        assert all(line.size is None for b in page.blocks for line in b.lines)
    assert doc.warnings == []


def test_ocr_failure_is_ocr_failed(tmp_path: Path) -> None:
    ocr = FakeOcr(fail=True)
    doc = parse_pdf(write_scanned_pdf(tmp_path / "scan.pdf"), ocr_engine=ocr)
    (page,) = doc.pages
    assert ocr.calls == 1
    assert page.extraction_status == PageExtractionStatus.OCR_FAILED
    assert page.ocr_used is False
    assert page.ocr_confidence is None
    assert any("OCR failed" in w for w in page.warnings)
    assert doc.warnings == ["1 page(s) could not be read: [0]"]


def test_unavailable_fake_ocr_is_not_called(tmp_path: Path) -> None:
    ocr = FakeOcr(available=False)
    doc = parse_pdf(write_scanned_pdf(tmp_path / "scan.pdf"), ocr_engine=ocr)
    assert ocr.calls == 0
    assert doc.pages[0].extraction_status == PageExtractionStatus.OCR_UNAVAILABLE


def test_blank_page_is_empty_and_not_ocrd(tmp_path: Path) -> None:
    ocr = FakeOcr()
    doc = parse_pdf(write_blank_pdf(tmp_path / "blank.pdf"), ocr_engine=ocr)
    (page,) = doc.pages
    assert ocr.calls == 0
    assert page.extraction_status == PageExtractionStatus.EMPTY
    assert page.displayed_page_number is None
    assert doc.warnings == []


def test_mixed_pdf_only_scanned_page_ocrd(tmp_path: Path) -> None:
    ocr = FakeOcr()
    doc = parse_pdf(write_mixed_pdf(tmp_path / "mixed.pdf"), ocr_engine=ocr)
    assert doc.page_count == 4
    assert ocr.calls == 1
    statuses = [p.extraction_status for p in doc.pages]
    assert statuses == [PageExtractionStatus.EXTRACTED] * 3 + [PageExtractionStatus.OCR_EXTRACTED]
    assert [p.ocr_used for p in doc.pages] == [False, False, False, True]
    # Text pages keep their footer numbers; the scanned page has none, so none is guessed.
    assert [p.displayed_page_number for p in doc.pages] == ["101", "102", "103", None]


# ----- Tesseract output grouping ------------------------------------------------------


def test_lines_from_tesseract_groups_words_and_averages_confidence() -> None:
    data = {
        "text": ["", "Hello", "world", "  ", "Second", "line"],
        "block_num": [0, 1, 1, 1, 1, 1],
        "par_num": [0, 1, 1, 1, 1, 1],
        "line_num": [0, 1, 1, 1, 2, 2],
        "conf": ["-1", "90", "80", "-1", "70", "-1"],
        "top": [0, 10, 12, 0, 40, 41],
        "height": [0, 20, 20, 0, 18, 20],
    }
    result = _lines_from_tesseract(data)
    assert [(line.text, line.y0, line.y1) for line in result.lines] == [
        ("Hello world", 10, 32),
        ("Second line", 40, 61),
    ]
    assert result.mean_confidence == pytest.approx(80.0)


def test_lines_from_tesseract_without_words_has_no_confidence() -> None:
    data = {
        "text": ["", " "],
        "block_num": [0, 1],
        "par_num": [0, 1],
        "line_num": [0, 1],
        "conf": ["-1", "-1"],
        "top": [0, 0],
        "height": [0, 0],
    }
    result = _lines_from_tesseract(data)
    assert result.lines == []
    assert result.mean_confidence is None


# ----- line joining -------------------------------------------------------------------


def test_join_lines_hyphenation_rules() -> None:
    assert join_lines(["the trans-", "former model"]) == "the transformer model"
    assert join_lines(["during COVID-", "19 lockdowns"]) == "during COVID-19 lockdowns"
    assert join_lines(["Hodgkin-", "Huxley model"]) == "Hodgkin-Huxley model"
    assert join_lines(["a", "", "   ", "b"]) == "a b"
    assert join_lines(["-", "word"]) == "- word"
    assert join_lines([]) == ""
