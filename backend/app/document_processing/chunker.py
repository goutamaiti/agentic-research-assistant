"""Section-aware chunking with page provenance.

Rules (specification §6.2):
- chunks never cross a section boundary;
- paragraphs are kept whole when they fit; an oversized paragraph is split at sentence
  boundaries, and only a single oversized sentence is split by words;
- consecutive chunks of a section overlap by whole trailing sentences (~overlap tokens);
- sizes are measured with the embedding model's tokenizer (injected as ``count_tokens``).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.document_processing.types import Chunk, Paragraph

TokenCounter = Callable[[str], int]

# Split after sentence-final punctuation followed by whitespace and an uppercase letter,
# digit, quote or bracket. Avoids splitting "e.g. the" and "et al. (2020)" in most cases.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")
_NO_SPLIT_BEFORE = re.compile(
    r"(?:\b(?:e\.g|i\.e|et al|etc|vs|fig|figs|eq|eqs|no|cf)\.)$", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    target_tokens: int = 220
    overlap_tokens: int = 40
    max_tokens: int = 256


@dataclass(slots=True)
class _Piece:
    text: str
    tokens: int
    page: int


def split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_END.split(text)
    sentences: list[str] = []
    for part in parts:
        if sentences and _NO_SPLIT_BEFORE.search(sentences[-1]):
            sentences[-1] = f"{sentences[-1]} {part}"
        else:
            sentences.append(part)
    return [s.strip() for s in sentences if s.strip()]


def _split_words(text: str, max_tokens: int, count: TokenCounter) -> list[str]:
    words = text.split()
    out: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and count(candidate) > max_tokens:
            out.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        out.append(" ".join(current))
    return out


def _pieces(paragraph: Paragraph, config: ChunkingConfig, count: TokenCounter) -> list[_Piece]:
    """A paragraph as one piece if it fits, else its sentences (or word windows)."""
    tokens = count(paragraph.text)
    if tokens <= config.target_tokens:
        return [_Piece(paragraph.text, tokens, paragraph.pdf_page_index)]
    pieces: list[_Piece] = []
    for sentence in split_sentences(paragraph.text):
        sentence_tokens = count(sentence)
        if sentence_tokens <= config.max_tokens:
            pieces.append(_Piece(sentence, sentence_tokens, paragraph.pdf_page_index))
        else:
            for window in _split_words(sentence, config.target_tokens, count):
                pieces.append(_Piece(window, count(window), paragraph.pdf_page_index))
    return pieces


def _overlap_tail(
    pieces: list[_Piece], config: ChunkingConfig, count: TokenCounter
) -> list[_Piece]:
    """Trailing whole sentences of the previous chunk, up to ``overlap_tokens``."""
    if config.overlap_tokens == 0 or not pieces:
        return []
    sentences: list[_Piece] = []
    for piece in pieces:
        sentences.extend(_Piece(s, count(s), piece.page) for s in split_sentences(piece.text))
    tail: list[_Piece] = []
    total = 0
    for sentence in reversed(sentences):
        if total + sentence.tokens > config.overlap_tokens:
            break
        tail.insert(0, sentence)
        total += sentence.tokens
    # Overlap that would repeat the whole previous chunk adds nothing.
    return tail if len(tail) < len(sentences) else []


def _join(pieces: Iterable[_Piece]) -> str:
    return " ".join(piece.text for piece in pieces)


def chunk_section(
    paragraphs: list[Paragraph],
    section_index: int,
    config: ChunkingConfig,
    count: TokenCounter,
) -> list[tuple[str, int, int, int]]:
    """Chunk one section. Returns (text, tokens, first page, last page) tuples."""
    pieces = [piece for paragraph in paragraphs for piece in _pieces(paragraph, config, count)]
    results: list[tuple[str, int, int, int]] = []
    current: list[_Piece] = []
    new_count = 0  # pieces in ``current`` that are not overlap carried from the last chunk

    def flush() -> None:
        text = _join(current)
        results.append((text, count(text), current[0].page, current[-1].page))

    for piece in pieces:
        candidate = _join([*current, piece])
        if current and new_count and count(candidate) > config.target_tokens:
            flush()
            tail = _overlap_tail(current, config, count)
            current = [*tail, piece]
            new_count = 1
            if count(_join(current)) > config.max_tokens:  # overlap would overflow
                current = [piece]
        else:
            current.append(piece)
            new_count += 1
    if current and new_count:
        text = _join(current)
        tokens = count(text)
        # Merge a short tail into the previous chunk when it still fits under the cap.
        if results and tokens < config.target_tokens // 4:
            prev_text, _, prev_start, _ = results[-1]
            merged = f"{prev_text} {_join(p for p in current[-new_count:])}"
            if count(merged) <= config.max_tokens:
                results[-1] = (merged, count(merged), prev_start, current[-1].page)
                return results
        results.append((text, tokens, current[0].page, current[-1].page))
    return results


def chunk_paragraphs(
    paragraphs: list[Paragraph],
    config: ChunkingConfig,
    count: TokenCounter,
) -> list[Chunk]:
    """Chunk all paragraphs section by section, numbering chunks in reading order."""
    by_section: dict[int, list[Paragraph]] = {}
    order: list[int] = []
    for paragraph in paragraphs:
        if paragraph.section_index not in by_section:
            by_section[paragraph.section_index] = []
            order.append(paragraph.section_index)
        by_section[paragraph.section_index].append(paragraph)

    chunks: list[Chunk] = []
    for section_index in order:
        for text, tokens, start, end in chunk_section(
            by_section[section_index], section_index, config, count
        ):
            chunks.append(
                Chunk(
                    chunk_index=len(chunks),
                    text=text,
                    token_count=tokens,
                    section_index=section_index,
                    pdf_page_start=start,
                    pdf_page_end=end,
                )
            )
    return chunks
