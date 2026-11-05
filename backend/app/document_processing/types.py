"""Plain data structures passed between document-processing steps.

These are internal and deliberately framework-free; API and persistence layers convert
them into Pydantic or ORM objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.database.models import PageExtractionStatus


@dataclass(slots=True)
class TextLine:
    """One visual line of text on a page."""

    text: str
    # Font size in points; None for OCR text, which has no reliable font information.
    size: float | None
    bold: bool
    y0: float
    y1: float


@dataclass(slots=True)
class TextBlock:
    """A block of consecutive lines as laid out on the page (roughly a paragraph)."""

    lines: list[TextLine]
    y0: float
    y1: float

    @property
    def text(self) -> str:
        return join_lines([line.text for line in self.lines])


@dataclass(slots=True)
class ParsedPage:
    pdf_page_index: int
    width: float
    height: float
    blocks: list[TextBlock]
    extraction_status: PageExtractionStatus
    ocr_used: bool = False
    ocr_confidence: float | None = None
    pdf_label: str | None = None  # page label stored in the PDF, if any
    displayed_page_number: str | None = None  # resolved later
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(block.text for block in self.blocks if block.text)


@dataclass(slots=True)
class ParsedDocument:
    page_count: int
    pages: list[ParsedPage]
    pdf_metadata: dict[str, str]
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Section:
    section_index: int
    title: str
    level: int
    section_type: str
    parent_index: int | None
    start_page_index: int
    end_page_index: int


@dataclass(slots=True)
class Paragraph:
    """A unit of body text assigned to a section, used as input to chunking."""

    text: str
    pdf_page_index: int
    section_index: int


@dataclass(slots=True)
class Chunk:
    chunk_index: int
    text: str
    token_count: int
    section_index: int
    pdf_page_start: int
    pdf_page_end: int


def join_lines(lines: list[str]) -> str:
    """Join visual lines into running text, repairing end-of-line hyphenation.

    ``"trans-" + "former"`` becomes ``"transformer"``; a hyphen followed by an uppercase
    word or a digit (``"COVID-" + "19"``) is kept.
    """
    out = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if not out:
            out = line
        elif out.endswith("-") and len(out) > 1 and out[-2].isalnum():
            # "trans-"+"former" -> "transformer"; "COVID-"+"19" -> "COVID-19";
            # "state-of-the-"+"art" -> "state-of-the-art" (already a hyphenated compound).
            fragment = out.rsplit(maxsplit=1)[-1][:-1]
            if line[:1].islower() and "-" not in fragment:
                out = out[:-1] + line
            else:
                out = out + line
        else:
            out = f"{out} {line}"
    return out
