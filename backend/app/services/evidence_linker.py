"""Deterministic linking of model-cited quotes to stored source text and PDF pages.

The model cites ``(passage_id, quote)``. This module checks the quote against the stored
chunk text (exactly, then after light normalisation), returns the exact source span, and
locates the PDF page it is on. A quote that cannot be found is recorded as ``not_found``
with **no** page or section, so a fabricated quote can never become a page citation
(spec §14, "Incorrect page mapping").
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.schemas.evidence import QuoteMatch

_CHAR_MAP = {
    "‘": "'",
    "’": "'",
    "‚": "'",
    "‛": "'",
    "′": "'",
    "“": '"',
    "”": '"',
    "„": '"',
    "″": '"',
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",
    "—": "-",
    "−": "-",
    " ": " ",
    " ": " ",
    " ": " ",
}
_DROP = {"­", "​", "‌", "‍", "﻿"}  # soft hyphen, zero-width chars
_EDGE_PUNCTUATION = " \t\n\"'.,;:!?()[]{}…"
# Shorter quotes ("see", "Table 2") match almost anywhere and prove nothing.
MIN_QUOTE_CHARS = 8


def normalise_with_map(text: str) -> tuple[str, list[int]]:
    """Lower-cased, whitespace-collapsed text plus, for each output character, the index
    of the original character it came from (ligatures such as "ﬁ" expand to "fi")."""
    out: list[str] = []
    index_map: list[int] = []
    previous_space = True
    for index, char in enumerate(text):
        if char in _DROP:
            continue
        char = _CHAR_MAP.get(char, char)
        expanded = unicodedata.normalize("NFKC", char) if ord(char) > 127 else char
        for piece in expanded.lower():
            if piece.isspace():
                if previous_space:
                    continue
                piece = " "
                previous_space = True
            else:
                previous_space = False
            out.append(piece)
            index_map.append(index)
    while out and out[-1] == " ":
        out.pop()
        index_map.pop()
    return "".join(out), index_map


def normalise(text: str) -> str:
    return normalise_with_map(text)[0]


def find_span(haystack: str, quote: str) -> tuple[str, QuoteMatch] | None:
    """Locate ``quote`` in ``haystack``; return the exact original span and match type."""
    quote = quote.strip()
    if len(normalise(quote)) < MIN_QUOTE_CHARS:
        return None
    if quote in haystack:
        return quote, QuoteMatch.EXACT
    norm_hay, index_map = normalise_with_map(haystack)
    for candidate in (quote, quote.strip(_EDGE_PUNCTUATION)):
        norm_quote = normalise(candidate)
        if len(norm_quote) < MIN_QUOTE_CHARS:
            continue
        start = norm_hay.find(norm_quote)
        if start >= 0:
            end = start + len(norm_quote) - 1
            return haystack[index_map[start] : index_map[end] + 1], QuoteMatch.NORMALIZED
    return None


@dataclass(frozen=True, slots=True)
class PassageSource:
    passage_id: str
    chunk_id: str
    text: str
    section_name: str | None
    pdf_page_start: int
    pdf_page_end: int


@dataclass(frozen=True, slots=True)
class ResolvedEvidence:
    source_text: str
    quote_match: QuoteMatch
    chunk_id: str | None = None
    pdf_page_index: int | None = None
    displayed_page_number: str | None = None
    section_name: str | None = None
    corrected_passage: bool = False  # the quote was found in a different passage


class EvidenceLinker:
    def __init__(
        self,
        passages: list[PassageSource],
        page_texts: dict[int, str],
        displayed_pages: dict[int, str | None],
    ) -> None:
        self._passages = {p.passage_id: p for p in passages}
        self._page_norm = {page: normalise(text) for page, text in page_texts.items()}
        self._displayed = displayed_pages

    def _page_of(self, passage: PassageSource, span: str) -> int:
        if passage.pdf_page_start == passage.pdf_page_end:
            return passage.pdf_page_start
        needle = normalise(span)
        for page in range(passage.pdf_page_start, passage.pdf_page_end + 1):
            if needle and needle in self._page_norm.get(page, ""):
                return page
        # The span crosses a page break; cite the page where the passage starts.
        return passage.pdf_page_start

    def _resolved(
        self, passage: PassageSource, span: str, match: QuoteMatch, corrected: bool
    ) -> ResolvedEvidence:
        page = self._page_of(passage, span)
        return ResolvedEvidence(
            source_text=span,
            quote_match=match,
            chunk_id=passage.chunk_id,
            pdf_page_index=page,
            displayed_page_number=self._displayed.get(page),
            section_name=passage.section_name,
            corrected_passage=corrected,
        )

    def resolve(self, passage_id: str, quote: str) -> ResolvedEvidence:
        cited = self._passages.get(passage_id.strip())
        if cited is not None:
            found = find_span(cited.text, quote)
            if found:
                return self._resolved(cited, *found, corrected=False)
        # The model may cite the wrong passage ID; accept only a match elsewhere.
        for passage in self._passages.values():
            if passage is cited:
                continue
            found = find_span(passage.text, quote)
            if found:
                return self._resolved(passage, *found, corrected=True)
        return ResolvedEvidence(
            source_text=re.sub(r"\s+", " ", quote).strip(), quote_match=QuoteMatch.NOT_FOUND
        )
