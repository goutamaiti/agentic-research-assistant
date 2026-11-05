"""PDF validation and page-wise text extraction (PyMuPDF), with OCR fallback.

PDF content is untrusted: only text and rendered images are read. Embedded scripts,
attachments, forms and links are never executed or extracted.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from app.database.models import PageExtractionStatus
from app.document_processing.ocr import OcrEngine, OcrError
from app.document_processing.types import ParsedDocument, ParsedPage, TextBlock, TextLine

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
# The PDF header may appear within the first 1024 bytes (PDF 1.7, Annex H).
HEADER_SEARCH_BYTES = 1024

_BOLD_FLAG = 1 << 4
_MARGIN_FRACTION = 0.08  # top/bottom band where running headers and page numbers live
# Upper bound on rendered pixels per OCR page (about 40 MP: an A4 page at ~760 dpi).
MAX_OCR_PIXELS = 40_000_000
_ROMAN = re.compile(r"^(?=[ivxlcdm]+$)m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$")
_ARABIC_PAGE = re.compile(r"^\d{1,4}$")


class PdfValidationError(ValueError):
    """The file is not a PDF this application can process."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(slots=True)
class PdfInfo:
    page_count: int


def has_pdf_header(head: bytes) -> bool:
    return PDF_MAGIC in head[:HEADER_SEARCH_BYTES]


def validate_pdf(path: Path) -> PdfInfo:
    """Check that ``path`` is a readable, unencrypted PDF with at least one page."""
    with path.open("rb") as handle:
        if not has_pdf_header(handle.read(HEADER_SEARCH_BYTES)):
            raise PdfValidationError("not_pdf", "The file is not a PDF (missing %PDF header).")
    try:
        doc = pymupdf.open(path, filetype="pdf")
    except Exception as exc:
        raise PdfValidationError(
            "corrupt_pdf", "The PDF is damaged or unreadable and cannot be processed."
        ) from exc
    with doc:
        if doc.needs_pass or doc.is_encrypted:
            raise PdfValidationError(
                "encrypted_pdf",
                "Password-protected or encrypted PDFs are not supported. "
                "Remove the protection and upload again.",
            )
        if doc.page_count < 1:
            # PyMuPDF silently "repairs" many damaged files into zero-page documents.
            if doc.is_repaired:
                raise PdfValidationError(
                    "corrupt_pdf", "The PDF is damaged or unreadable and cannot be processed."
                )
            raise PdfValidationError("empty_pdf", "The PDF has no pages.")
        try:
            doc.load_page(0).get_text("text")
        except Exception as exc:
            raise PdfValidationError(
                "corrupt_pdf", "The PDF is damaged or unreadable and cannot be processed."
            ) from exc
        return PdfInfo(page_count=doc.page_count)


def _row_text(spans: list[dict]) -> str:
    """Join spans left to right, inserting a space where there is a visible gap.

    LaTeX often positions words (e.g. a section number and its title) as separate spans
    with no space character between them.
    """
    text = ""
    previous: dict | None = None
    for span in sorted(spans, key=lambda s: s["bbox"][0]):
        piece = span["text"]
        if previous is not None:
            gap = span["bbox"][0] - previous["bbox"][2]
            if gap > 0.15 * min(span["size"], previous["size"]) and not (
                text.endswith(" ") or piece.startswith(" ")
            ):
                text += " "
        text += piece
        previous = span
    return re.sub(r"\s+", " ", text).strip()


def _make_line(spans: list[dict], y0: float, y1: float) -> TextLine:
    chars = sum(len(span["text"].strip()) for span in spans)
    # Character-weighted font size and boldness for the line.
    size = sum(span["size"] * len(span["text"].strip()) for span in spans) / chars
    bold_chars = sum(
        len(span["text"].strip())
        for span in spans
        if span["flags"] & _BOLD_FLAG or "bold" in span.get("font", "").lower()
    )
    return TextLine(
        text=_row_text(spans), size=round(size, 2), bold=bold_chars > chars / 2, y0=y0, y1=y1
    )


def _blocks_from_text_layer(page: pymupdf.Page) -> tuple[list[TextBlock], int]:
    """Text blocks of a page, plus the number of non-horizontal lines left out.

    Vertical or rotated text (arXiv margin stamps, axis labels inside figures) is not body
    text and is excluded. Fragments that PyMuPDF reports as separate lines on the same
    baseline (e.g. "1" and "Introduction") are merged into one visual line.
    """
    data = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_LIGATURES)
    blocks: list[TextBlock] = []
    skipped = 0
    for block in data.get("blocks", []):
        if block.get("type") != 0:  # 0 = text; images are ignored here
            continue
        rows: list[tuple[list[dict], float, float, float]] = []  # spans, y0, y1, x1
        for line in block.get("lines", []):
            spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
            if not spans:
                continue
            dx, dy = line.get("dir", (1.0, 0.0))
            if abs(dy) > 0.1 or dx < 0.9:
                skipped += 1
                continue
            x0, y0, x1, y1 = line["bbox"]
            size = max(span["size"] for span in spans)
            if rows:
                row_spans, row_y0, row_y1, row_x1 = rows[-1]
                same_baseline = abs(y0 - row_y0) < 0.5 * size and abs(y1 - row_y1) < 0.5 * size
                if same_baseline and x0 >= row_x1 - 1.0:
                    rows[-1] = (row_spans + spans, min(row_y0, y0), max(row_y1, y1), x1)
                    continue
            rows.append((spans, y0, y1, x1))
        lines = [_make_line(spans, y0, y1) for spans, y0, y1, _ in rows]
        lines = [line for line in lines if line.text]
        if lines:
            blocks.append(TextBlock(lines=lines, y0=lines[0].y0, y1=lines[-1].y1))
    return blocks, skipped


def _page_has_images(page: pymupdf.Page) -> bool:
    return bool(page.get_images(full=False))


def _ocr_page(
    page: pymupdf.Page, engine: OcrEngine, dpi: int
) -> tuple[list[TextBlock], float | None]:
    # Cap the rendered size: a small PDF can declare an enormous page.
    width_in, height_in = page.rect.width / 72, page.rect.height / 72
    dpi = min(dpi, int(math.sqrt(MAX_OCR_PIXELS / max(width_in * height_in, 1e-6))))
    if dpi < 72:
        raise OcrError("page is too large to render for OCR")
    try:
        pixmap = page.get_pixmap(dpi=dpi)
        png = pixmap.tobytes("png")
    except Exception as exc:
        raise OcrError(f"page could not be rendered ({type(exc).__name__})") from exc
    result = engine.recognize(png)
    # OCR coordinates are in the rendered (rotated) image; scale them to points.
    scale = page.rect.height / pixmap.height if pixmap.height else 1.0
    blocks = [
        TextBlock(
            lines=[
                TextLine(
                    text=line.text, size=None, bold=False, y0=line.y0 * scale, y1=line.y1 * scale
                )
            ],
            y0=line.y0 * scale,
            y1=line.y1 * scale,
        )
        for line in result.lines
        if line.text.strip()
    ]
    return blocks, result.mean_confidence


def parse_pdf(
    path: Path,
    *,
    ocr_engine: OcrEngine | None,
    ocr_min_text_chars: int = 40,
    ocr_dpi: int = 300,
) -> ParsedDocument:
    """Extract page-wise text.

    A page is treated as scanned when it contains images and too little text; only those
    pages are OCR'd. A short page without images (a caption, a heading) keeps its text.
    """
    warnings: list[str] = []
    pages: list[ParsedPage] = []
    ocr_ready = ocr_engine is not None and ocr_engine.is_available()

    with pymupdf.open(path, filetype="pdf") as doc:
        metadata = {key: value for key, value in (doc.metadata or {}).items() if value}
        for index in range(doc.page_count):
            page = doc.load_page(index)
            label = (page.get_label() or "").strip() or None
            blocks, skipped_vertical = _blocks_from_text_layer(page)
            char_count = sum(len(block.text) for block in blocks)
            # Text-layer coordinates are in the unrotated page space (the cropbox).
            parsed = ParsedPage(
                pdf_page_index=index,
                width=page.cropbox.width,
                height=page.cropbox.height,
                blocks=blocks,
                extraction_status=PageExtractionStatus.EXTRACTED,
                pdf_label=label,
            )
            if skipped_vertical:
                parsed.warnings.append(
                    f"{skipped_vertical} vertical/rotated text line(s) excluded "
                    "(margin stamps or figure labels)."
                )
            if char_count < ocr_min_text_chars and _page_has_images(page):
                if not ocr_ready:
                    parsed.extraction_status = PageExtractionStatus.OCR_UNAVAILABLE
                    parsed.warnings.append(
                        "Page looks scanned (images, little text) and OCR is not available."
                    )
                else:
                    try:
                        ocr_blocks, confidence = _ocr_page(page, ocr_engine, ocr_dpi)
                    except OcrError as exc:
                        ocr_blocks, confidence = [], None
                        parsed.warnings.append(f"OCR failed: {exc}")
                    ocr_chars = sum(len(block.text) for block in ocr_blocks)
                    if ocr_chars > char_count:
                        parsed.blocks = ocr_blocks
                        parsed.width, parsed.height = page.rect.width, page.rect.height
                        parsed.ocr_used = True
                        parsed.ocr_confidence = confidence
                        parsed.extraction_status = PageExtractionStatus.OCR_EXTRACTED
                    else:
                        parsed.extraction_status = PageExtractionStatus.OCR_FAILED
                        parsed.warnings.append("OCR produced no usable text.")
            elif char_count == 0:
                parsed.extraction_status = PageExtractionStatus.EMPTY
            pages.append(parsed)

    resolve_displayed_page_numbers(pages)
    unreadable = [
        p.pdf_page_index
        for p in pages
        if p.extraction_status
        in (PageExtractionStatus.OCR_FAILED, PageExtractionStatus.OCR_UNAVAILABLE)
    ]
    if unreadable:
        warnings.append(f"{len(unreadable)} page(s) could not be read: {unreadable}")
    logger.info(
        "Parsed PDF: pages=%d ocr_pages=%d unreadable=%d",
        len(pages),
        sum(p.ocr_used for p in pages),
        len(unreadable),
    )
    return ParsedDocument(
        page_count=len(pages), pages=pages, pdf_metadata=metadata, warnings=warnings
    )


# ----- Displayed (printed) page numbers -------------------------------------------------


def margin_lines(page: ParsedPage) -> list[str]:
    band = page.height * _MARGIN_FRACTION
    return [
        line.text.strip()
        for block in page.blocks
        for line in block.lines
        if line.y1 <= band or line.y0 >= page.height - band
    ]


def _page_number_candidates(page: ParsedPage) -> list[str]:
    candidates = []
    for text in margin_lines(page):
        cleaned = text.strip().strip("-–— ").lower()
        if _ARABIC_PAGE.match(cleaned) or (cleaned and _ROMAN.match(cleaned)):
            candidates.append(cleaned)
    return candidates


def resolve_displayed_page_numbers(pages: list[ParsedPage]) -> None:
    """Set ``displayed_page_number`` only when it can be identified with confidence.

    1. A page label stored in the PDF is used as-is.
    2. Otherwise, a standalone number printed in the header/footer band is used when it is
       consistent with the offset shared by most numbered pages (so a stray number in a
       table or figure does not create a false page reference).
    Pages without a confident number keep ``None``; a number is never guessed.
    """
    if pages and all(p.pdf_label for p in pages):
        for page in pages:
            page.displayed_page_number = page.pdf_label
        return

    offsets: Counter[int] = Counter()
    per_page: dict[int, list[int]] = {}
    for page in pages:
        numbers = [int(c) for c in _page_number_candidates(page) if c.isdigit()]
        per_page[page.pdf_page_index] = numbers
        for number in set(numbers):
            offsets[number - page.pdf_page_index] += 1

    offset, support = (offsets.most_common(1) or [(0, 0)])[0]
    numbered_pages = sum(1 for numbers in per_page.values() if numbers)
    confident = support >= 2 and support >= 0.5 * numbered_pages

    for page in pages:
        if page.pdf_label:
            page.displayed_page_number = page.pdf_label
        elif confident and (page.pdf_page_index + offset) in per_page[page.pdf_page_index]:
            page.displayed_page_number = str(page.pdf_page_index + offset)
        else:
            page.displayed_page_number = None


# ----- Repeated running headers/footers --------------------------------------------------


def _normalise_boilerplate(text: str) -> str:
    return re.sub(r"\d+", "#", text.strip().lower())


def find_boilerplate_lines(pages: list[ParsedPage], min_fraction: float = 0.4) -> set[str]:
    """Return normalised margin lines repeated on many pages (running headers/footers)."""
    if len(pages) < 3:
        return set()
    counts: Counter[str] = Counter()
    for page in pages:
        counts.update({_normalise_boilerplate(text) for text in margin_lines(page) if text})
    threshold = max(3, int(min_fraction * len(pages)))
    return {text for text, count in counts.items() if count >= threshold}


def is_boilerplate(line: TextLine, page: ParsedPage, boilerplate: set[str]) -> bool:
    band = page.height * _MARGIN_FRACTION
    in_margin = line.y1 <= band or line.y0 >= page.height - band
    if not in_margin:
        return False
    normalised = _normalise_boilerplate(line.text)
    if normalised in boilerplate:
        return True
    cleaned = line.text.strip().strip("-–— ").lower()
    return bool(_ARABIC_PAGE.match(cleaned) or (cleaned and _ROMAN.match(cleaned)))
