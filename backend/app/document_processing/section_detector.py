"""Deterministic section and subsection identification.

Signals used, in order of reliability:
1. numbered headings ("3", "3.2", "IV.") that are also styled as headings (bold/larger);
2. well-known academic section names ("Abstract", "Related Work", "References", ...);
3. short unnumbered lines that are clearly bolder/larger than the body text.

The text before the first heading becomes an implicit "Front matter" section (title,
authors, affiliations). Detection is heuristic; see DEVELOPMENT_LOG.md for limitations.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from app.document_processing.pdf_parser import is_boilerplate
from app.document_processing.types import (
    Paragraph,
    ParsedDocument,
    Section,
    TextBlock,
    TextLine,
    join_lines,
)

FRONT_MATTER = "front_matter"

# Canonical section types, matched against the lower-cased heading title (first match wins).
_SECTION_TYPES: list[tuple[str, tuple[str, ...]]] = [
    ("abstract", ("abstract",)),
    ("references", ("references", "bibliography", "works cited", "literature cited")),
    ("acknowledgments", ("acknowledgment", "acknowledgement")),
    ("appendix", ("appendix", "appendices", "supplementary")),
    ("future_work", ("future work", "future scope", "future direction", "future research")),
    ("limitations", ("limitation", "threats to validity")),
    ("conclusion", ("conclusion", "concluding", "summary and")),
    ("discussion", ("discussion",)),
    ("results", ("result", "finding", "performance", "analysis")),
    (
        "experiments",
        ("experiment", "evaluation", "setup", "dataset", "data set", "benchmark", "implementation"),
    ),
    (
        "related_work",
        (
            "related work",
            "literature",
            "background",
            "prior work",
            "previous work",
            "preliminar",
            "state of the art",
        ),
    ),
    ("introduction", ("introduction", "overview", "motivation")),
    (
        "methodology",
        (
            "method",
            "approach",
            "proposed",
            "model",
            "framework",
            "architecture",
            "system",
            "algorithm",
            "design",
            "technique",
        ),
    ),
]

# Names accepted as headings even without numbering (they must still stand alone).
_KNOWN_HEADINGS = {
    "abstract",
    "introduction",
    "background",
    "related work",
    "related works",
    "literature review",
    "methods",
    "method",
    "methodology",
    "materials and methods",
    "approach",
    "proposed method",
    "proposed approach",
    "experiments",
    "experiment",
    "experimental setup",
    "experimental results",
    "evaluation",
    "results",
    "results and discussion",
    "discussion",
    "conclusion",
    "conclusions",
    "conclusion and future work",
    "conclusions and future work",
    "future work",
    "limitations",
    "acknowledgments",
    "acknowledgements",
    "acknowledgment",
    "acknowledgement",
    "references",
    "bibliography",
    "appendix",
}

_NUMBERED = re.compile(r"^(?P<num>\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+(?P<title>\S.*)$")
_ROMAN_NUMBERED = re.compile(r"^(?P<num>[IVX]{1,5})\.\s+(?P<title>\S.*)$")
_LETTER_NUMBERED = re.compile(r"^(?P<num>[A-H])\.\s+(?P<title>[A-Z].*)$")
_INLINE_ABSTRACT = re.compile(r"^(abstract|summary)\s*[—–:.\-]\s*(?P<rest>\S.*)$", re.IGNORECASE)
_APPENDIX = re.compile(r"^appendix(\s+[A-Z0-9]+)?\b", re.IGNORECASE)


def classify_section(title: str) -> str:
    lowered = title.lower()
    for section_type, keywords in _SECTION_TYPES:
        if any(keyword in lowered for keyword in keywords):
            return section_type
    return "other"


def body_font_size(document: ParsedDocument) -> float | None:
    """Most common (character-weighted) font size: the body text size."""
    counts: Counter[float] = Counter()
    for page in document.pages:
        for block in page.blocks:
            for line in block.lines:
                if line.size is not None:
                    counts[round(line.size * 2) / 2] += len(line.text)
    return counts.most_common(1)[0][0] if counts else None


@dataclass(slots=True)
class _Heading:
    title: str
    level: int
    numbered: bool


def _strip_number(text: str) -> tuple[str | None, str]:
    for pattern in (_NUMBERED, _ROMAN_NUMBERED, _LETTER_NUMBERED):
        match = pattern.match(text)
        if match:
            return match.group("num"), match.group("title").strip()
    return None, text.strip()


def _looks_like_heading_text(text: str) -> bool:
    words = text.split()
    return (
        0 < len(words) <= 14
        and len(text) <= 120
        and any(ch.isalpha() for ch in text)
        and not text.rstrip().endswith((",", ";", ":"))
        # A heading is not a sentence: a trailing period after several words is body text.
        and not (text.rstrip().endswith(".") and len(words) > 3)
    )


def _emphasised(line: TextLine, body_size: float | None) -> bool:
    if line.size is None or body_size is None:
        return line.text.isupper() and len(line.text) > 3
    return line.bold or line.size >= body_size * 1.1 or (line.text.isupper() and len(line.text) > 3)


def _heading_level_for_number(num: str) -> int:
    if num.isdigit() or re.fullmatch(r"[IVX]+", num):
        return 1
    if re.fullmatch(r"[A-H]", num):
        return 2
    return min(1 + num.count("."), 3)


def _detect_heading(
    line: TextLine,
    block: TextBlock,
    body_size: float | None,
    *,
    seen_structured_heading: bool,
    large_heading_size: float | None,
    repeated_texts: frozenset[str] = frozenset(),
) -> _Heading | None:
    text = line.text.strip()
    if not _looks_like_heading_text(text):
        return None
    num, title = _strip_number(text)
    title_key = re.sub(r"\s+", " ", title.lower()).strip(" .")
    known = title_key in _KNOWN_HEADINGS or bool(_APPENDIX.match(title_key))
    standalone = len(block.lines) == 1 or line is block.lines[0]
    emphasised = _emphasised(line, body_size)

    if num is not None:
        starts_upper = title[:1].isupper()
        if starts_upper and (emphasised or known):
            return _Heading(title=title, level=_heading_level_for_number(num), numbered=True)
        return None
    if known and standalone and (emphasised or len(block.lines) == 1):
        return _Heading(title=title, level=1, numbered=False)
    # Unnumbered styled headings are only trusted once the paper's structure has started,
    # so the title and author lines on the first page are not mistaken for sections.
    # Text that occurs several times (labels inside figures, repeated captions) is not a
    # section heading.
    if (
        seen_structured_heading
        and title_key not in repeated_texts
        and len(block.lines) <= 2
        and line is block.lines[0]
        and line.size is not None
        and body_size is not None
        and (line.size >= body_size * 1.15 or (line.bold and len(text.split()) <= 8))
    ):
        level = 1 if large_heading_size and line.size >= large_heading_size - 0.25 else 2
        return _Heading(title=title, level=level, numbered=False)
    return None


@dataclass(slots=True)
class DocumentStructure:
    sections: list[Section]
    paragraphs: list[Paragraph]
    body_font_size: float | None


def _repeated_line_texts(document: ParsedDocument) -> frozenset[str]:
    counts: Counter[str] = Counter(
        re.sub(r"\s+", " ", line.text.lower()).strip(" .")
        for page in document.pages
        for block in page.blocks
        for line in block.lines
    )
    return frozenset(text for text, count in counts.items() if count > 1)


def detect_structure(document: ParsedDocument, boilerplate: set[str]) -> DocumentStructure:
    body_size = body_font_size(document)
    repeated = _repeated_line_texts(document)
    sections: list[Section] = [Section(0, "Front matter", 1, FRONT_MATTER, None, 0, 0)]
    paragraphs: list[Paragraph] = []
    current = 0
    seen_structured = False
    large_heading_size: float | None = None

    def open_section(heading: _Heading, page_index: int) -> int:
        level = heading.level
        parent = next((s.section_index for s in reversed(sections[1:]) if s.level < level), None)
        section_type = classify_section(heading.title)
        if section_type == "other" and parent is not None:
            section_type = sections[parent].section_type
        sections.append(
            Section(
                len(sections), heading.title, level, section_type, parent, page_index, page_index
            )
        )
        return len(sections) - 1

    for page in document.pages:
        for block in page.blocks:
            lines = [line for line in block.lines if not is_boilerplate(line, page, boilerplate)]
            if not lines:
                continue
            block = TextBlock(lines=lines, y0=lines[0].y0, y1=lines[-1].y1)
            first = lines[0]
            body_lines = lines

            inline = _INLINE_ABSTRACT.match(first.text.strip())
            heading = None
            if inline and current == 0:
                heading = _Heading("Abstract", 1, False)
                body_lines = [
                    TextLine(inline.group("rest"), first.size, first.bold, first.y0, first.y1),
                    *lines[1:],
                ]
            else:
                heading = _detect_heading(
                    first,
                    block,
                    body_size,
                    seen_structured_heading=seen_structured,
                    large_heading_size=large_heading_size,
                    repeated_texts=repeated,
                )
                if heading:
                    # Wrapped long headings continue on following lines with the same style.
                    rest = lines[1:]
                    while (
                        rest
                        and first.size is not None
                        and rest[0].size == first.size
                        and rest[0].bold == first.bold
                        and len(heading.title) < 60
                        and _looks_like_heading_text(rest[0].text)
                        and first.size != body_size
                    ):
                        heading.title = f"{heading.title} {rest[0].text.strip()}"
                        rest = rest[1:]
                    body_lines = rest

            if heading:
                current = open_section(heading, page.pdf_page_index)
                if heading.numbered or classify_section(heading.title) != "other":
                    seen_structured = True
                    if heading.level == 1 and first.size is not None:
                        large_heading_size = max(large_heading_size or 0.0, first.size)

            text = join_lines([line.text for line in body_lines])
            if text:
                paragraphs.append(
                    Paragraph(text=text, pdf_page_index=page.pdf_page_index, section_index=current)
                )
                sections[current].end_page_index = max(
                    sections[current].end_page_index, page.pdf_page_index
                )

    # A parent section spans at least as far as its last subsection.
    for section in reversed(sections):
        if section.parent_index is not None:
            parent = sections[section.parent_index]
            parent.end_page_index = max(parent.end_page_index, section.end_page_index)

    return DocumentStructure(sections=sections, paragraphs=paragraphs, body_font_size=body_size)
