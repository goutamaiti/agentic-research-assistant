"""Deterministic publication-metadata extraction.

Only explicit evidence is used. A field with no explicit evidence stays ``not_found``;
nothing is guessed from file dates, filenames or general knowledge.
"""

from __future__ import annotations

import re

from app.document_processing.pdf_parser import is_boilerplate, margin_lines
from app.document_processing.section_detector import FRONT_MATTER, DocumentStructure
from app.document_processing.types import ParsedDocument, join_lines
from app.schemas.paper import DocumentMetadata, ExtractionStatus, MetadataField

DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)
# A DOI in the text counts as the paper's own only when it is explicitly labelled.
_LABELLED_DOI = re.compile(
    r"(?:\bdoi\s*[:.]?\s*|doi\.org/)(?P<doi>10\.\d{4,9}/[^\s\"<>]+)", re.IGNORECASE
)
_DOI_TRAILING = ".,;:)]}'\""
_KEYWORDS = re.compile(r"^(?:key\s?words|index terms)\s*[—–:.\-]?\s*(?P<rest>.+)$", re.IGNORECASE)
_YEAR_PATTERNS = [
    re.compile(
        r"(?:©|\bcopyright\b(?:\s*©)?|^\(c\))\s*(?P<year>(?:19|20)\d{2})\b",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(
        r"\bpublished(?:\s+online)?\s*:?\s*(?:\w+\s+){0,3}(?P<year>(?:19|20)\d{2})\b", re.IGNORECASE
    ),
]
_BAD_PDF_TITLES = re.compile(
    r"^(untitled|microsoft word|document\d*|title|paper|manuscript|\S+\.(docx?|pdf|tex))\b",
    re.IGNORECASE,
)
_ENGLISH_STOPWORDS = frozenset(
    "the of and to in a is that for on with as by this are we be from an which or at it "
    "our can not has have these their was were its using based than also such".split()
)


def _clean_doi(raw: str) -> str:
    return raw.rstrip(_DOI_TRAILING)


def _title_from_layout(document: ParsedDocument, boilerplate: set[str]) -> tuple[str, str] | None:
    """Largest-font text in the top half of page 1, as (title, evidence)."""
    if not document.pages:
        return None
    page = document.pages[0]
    lines = [
        line
        for block in page.blocks
        for line in block.lines
        if line.size is not None
        and line.y0 < page.height * 0.5
        and not is_boilerplate(line, page, boilerplate)
        and any(ch.isalpha() for ch in line.text)
    ]
    if not lines:
        return None
    largest = max(line.size for line in lines)
    sizes = sorted({line.size for line in lines})
    # The title must stand out from the rest of the first page.
    if len(sizes) < 2 or largest < sizes[-2] + 1.0:
        return None
    title_lines: list[str] = []
    for line in lines:
        if abs(line.size - largest) < 0.5:
            title_lines.append(line.text)
        elif title_lines:
            break
    title = join_lines(title_lines)
    if not (3 <= len(title) <= 300):
        return None
    return title, "\n".join(title_lines)


def _title(document: ParsedDocument, boilerplate: set[str]) -> MetadataField[str]:
    layout = _title_from_layout(document, boilerplate)
    if layout:
        title, evidence = layout
        return MetadataField[str](
            value=title,
            status=ExtractionStatus.EXTRACTED,
            source="first_page_layout",
            pdf_page_index=0,
            evidence_text=evidence,
        )
    pdf_title = document.pdf_metadata.get("title", "").strip()
    if len(pdf_title) >= 8 and not _BAD_PDF_TITLES.match(pdf_title):
        return MetadataField[str](
            value=pdf_title,
            status=ExtractionStatus.EXTRACTED,
            source="pdf_metadata",
            evidence_text=pdf_title,
            note="Taken from the PDF's embedded metadata; not visible on the page.",
        )
    return MetadataField[str]()


def _split_authors(raw: str) -> list[str] | None:
    """Split an author string; None when the format is ambiguous ("Smith, John")."""
    if ";" in raw:
        parts = re.split(r";|\band\b|&", raw)
    else:
        parts = re.split(r",|\band\b|&", raw)
    names = [name.strip() for name in parts if name.strip()]
    # A single-word part means commas probably separate surname and given name.
    if ";" not in raw and "," in raw and any(len(name.split()) == 1 for name in names):
        return None
    return names or None


def _authors(document: ParsedDocument) -> MetadataField[list[str]]:
    raw = document.pdf_metadata.get("author", "").strip()
    if raw:
        names = _split_authors(raw)
        if names is None:
            return MetadataField[list[str]](
                value=[raw],
                status=ExtractionStatus.AMBIGUOUS,
                source="pdf_metadata",
                evidence_text=raw,
                note="The PDF metadata author string could not be split reliably.",
            )
        return MetadataField[list[str]](
            value=names,
            status=ExtractionStatus.EXTRACTED,
            source="pdf_metadata",
            evidence_text=raw,
            note="Taken from the PDF's embedded metadata; verify against the paper.",
        )
    return MetadataField[list[str]](
        note="Author names are not identified by deterministic parsing; "
        "resolved by the extraction phase."
    )


def _front_matter_texts(
    document: ParsedDocument, structure: DocumentStructure
) -> list[tuple[int, str]]:
    """Text where a paper states its own DOI/year: front matter and page margins (pages 1-2).

    Body text is excluded, so cited years and DOIs of datasets or other papers are not
    mistaken for this paper's metadata.
    """
    texts = [
        (p.pdf_page_index, p.text)
        for p in structure.paragraphs
        if p.pdf_page_index < 2 and structure.sections[p.section_index].section_type == FRONT_MATTER
    ]
    for page in document.pages[:2]:
        texts.extend((page.pdf_page_index, text) for text in margin_lines(page))
    return texts


def _doi(document: ParsedDocument, structure: DocumentStructure) -> MetadataField[str]:
    for page_index, text in _front_matter_texts(document, structure):
        match = _LABELLED_DOI.search(text)
        if match:
            return MetadataField[str](
                value=_clean_doi(match.group("doi")),
                status=ExtractionStatus.EXTRACTED,
                source="text_pattern",
                pdf_page_index=page_index,
                evidence_text=match.group(0),
            )
    for key in ("subject", "keywords"):
        match = DOI_PATTERN.search(document.pdf_metadata.get(key, ""))
        if match:
            return MetadataField[str](
                value=_clean_doi(match.group(0)),
                status=ExtractionStatus.EXTRACTED,
                source="pdf_metadata",
                evidence_text=match.group(0),
            )
    return MetadataField[str](
        note="No labelled DOI in the front matter; DOIs in body text are not used."
    )


def _publication_year(document: ParsedDocument, structure: DocumentStructure) -> MetadataField[int]:
    for page_index, text in _front_matter_texts(document, structure):
        for pattern in _YEAR_PATTERNS:
            match = pattern.search(text)
            if match:
                return MetadataField[int](
                    value=int(match.group("year")),
                    status=ExtractionStatus.EXTRACTED,
                    source="text_pattern",
                    pdf_page_index=page_index,
                    evidence_text=match.group(0),
                )
    return MetadataField[int](
        note="No explicit copyright/publication statement in the front matter; "
        "file dates and cited years are not used."
    )


def _abstract(structure: DocumentStructure) -> MetadataField[str]:
    section = next((s for s in structure.sections if s.section_type == "abstract"), None)
    if section is None:
        return MetadataField[str]()
    paragraphs = [p for p in structure.paragraphs if p.section_index == section.section_index]
    # Keyword lines often sit inside the abstract section; they are not abstract text.
    body = [p for p in paragraphs if not _KEYWORDS.match(p.text)]
    if not body:
        return MetadataField[str](
            status=ExtractionStatus.AMBIGUOUS,
            source="section_text",
            pdf_page_index=section.start_page_index,
            note="An abstract heading was found but no abstract text followed it.",
        )
    text = "\n\n".join(p.text for p in body)
    return MetadataField[str](
        value=text,
        status=ExtractionStatus.EXTRACTED,
        source="section_text",
        pdf_page_index=body[0].pdf_page_index,
        evidence_text=text,
    )


def _keywords(structure: DocumentStructure) -> MetadataField[list[str]]:
    for paragraph in structure.paragraphs[:80]:
        match = _KEYWORDS.match(paragraph.text)
        if match:
            parts = re.split(r"[;,·•]|\s[—–]\s", match.group("rest"))
            keywords = [part.strip(" .") for part in parts if part.strip(" .")]
            if keywords:
                return MetadataField[list[str]](
                    value=keywords,
                    status=ExtractionStatus.EXTRACTED,
                    source="text_pattern",
                    pdf_page_index=paragraph.pdf_page_index,
                    evidence_text=paragraph.text,
                )
    return MetadataField[list[str]]()


def _language(document: ParsedDocument) -> MetadataField[str]:
    words = re.findall(r"[a-z]+", " ".join(page.text for page in document.pages).lower())
    if len(words) < 50:
        return MetadataField[str](note="Too little text to determine the language.")
    ratio = sum(word in _ENGLISH_STOPWORDS for word in words) / len(words)
    if ratio >= 0.15:
        return MetadataField[str](
            value="en",
            status=ExtractionStatus.EXTRACTED,
            source="text_pattern",
            note=f"English function-word ratio {ratio:.2f} (heuristic).",
        )
    return MetadataField[str](
        status=ExtractionStatus.AMBIGUOUS,
        note=f"Low English function-word ratio {ratio:.2f}; the paper may not be English.",
    )


def extract_metadata(
    document: ParsedDocument, structure: DocumentStructure, boilerplate: set[str]
) -> DocumentMetadata:
    return DocumentMetadata(
        title=_title(document, boilerplate),
        authors=_authors(document),
        publication_year=_publication_year(document, structure),
        journal_or_conference=MetadataField[str](
            note="Venue is not identified by deterministic parsing; "
            "resolved by the extraction phase."
        ),
        doi=_doi(document, structure),
        abstract=_abstract(structure),
        keywords=_keywords(structure),
        document_language=_language(document),
    )
