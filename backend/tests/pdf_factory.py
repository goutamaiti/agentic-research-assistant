"""Synthetic PDFs for tests. All content is invented test text, not a real paper."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf

PAGE_W, PAGE_H = 595, 842  # A4 in points
MARGIN = 60
BODY = 10
RUNNING_HEADER = "Synthetic Journal of Retrieval Testing"

TITLE = "Hybrid Retrieval for Grounded Question Answering over Scientific Papers"
AUTHORS = "Ada Example and Brian Placeholder"
DOI = "10.5555/sjrt.2024.0042"

ABSTRACT = (
    "We study retrieval for answering questions about a single scientific paper. "
    "Our approach combines dense passage embeddings with sparse keyword ranking. "
    "Experiments on a synthetic benchmark show that the hybrid retriever improves recall "
    "over either retriever alone."
)
KEYWORDS = "Keywords: retrieval augmented generation, BM25, dense embeddings, citations"

INTRO = [
    "Researchers spend considerable time reading papers to locate problem statements, "
    "methods and results. Automated assistants can help, but fluent answers are not always "
    "grounded in the source document.",
    "This paper addresses grounded answering, where every statement must point to a page "
    "and passage in the uploaded paper. We motivate the problem with examples from survey "
    "articles and describe why citation accuracy matters for students.",
]
RELATED = [
    "Sparse lexical ranking functions such as BM25 score passages by term frequency and "
    "inverse document frequency. They remain strong baselines for exact keyword matching of "
    "technical terms and abbreviations.",
    "Dense retrievers encode questions and passages into a shared vector space. Bi-encoder "
    "models trained on question answering pairs retrieve paraphrased passages that share "
    "few words with the query.",
]
METHOD = [
    "The proposed pipeline has three stages. First, the document is split into "
    "section-aware chunks. Second, each chunk is embedded with a sentence encoder. Third, "
    "candidate passages from both retrievers are fused with reciprocal rank fusion.",
]
METHOD_SUB = [
    "During preprocessing we remove running headers and page numbers, repair hyphenated "
    "line breaks, and keep paragraph boundaries so that chunks remain readable.",
]
EXPERIMENTS = [
    "We evaluate on forty questions written by two annotators for a held-out paper. Each "
    "question is labelled with the passages that answer it. We report recall at five and "
    "mean reciprocal rank.",
]
RESULTS = [
    "The hybrid retriever reached a recall at five of 0.82 compared with 0.71 for dense "
    "retrieval alone and 0.64 for BM25 alone under the same question set.",
]
CONCLUSION = [
    "Combining sparse and dense retrieval gives more complete evidence for grounded "
    "answers. Future work will study reranking and table extraction.",
]
REFERENCES = [
    "[1] S. Robertson and H. Zaragoza. The probabilistic relevance framework: BM25 and "
    "beyond. Foundations and Trends in Information Retrieval, 2009.",
    "[2] N. Reimers and I. Gurevych. Sentence embeddings using siamese networks. 2019.",
]


@dataclass
class _Cursor:
    page: pymupdf.Page
    y: float


class PaperWriter:
    """Writes text top-to-bottom with automatic page breaks."""

    def __init__(self, *, running_header: bool = True, footer_start: int | None = None) -> None:
        self.doc = pymupdf.open()
        self.running_header = running_header
        self.footer_start = footer_start
        self.cursor = self._new_page()

    def _new_page(self) -> _Cursor:
        page = self.doc.new_page(width=PAGE_W, height=PAGE_H)
        index = self.doc.page_count - 1
        if self.running_header:
            page.insert_text((MARGIN, 30), RUNNING_HEADER, fontsize=8, fontname="helv")
        if self.footer_start is not None:
            page.insert_text(
                (PAGE_W / 2, PAGE_H - 25),
                str(self.footer_start + index),
                fontsize=8,
                fontname="helv",
            )
        return _Cursor(page=page, y=MARGIN + 10)

    def write(self, text: str, *, size: float = BODY, bold: bool = False, gap: float = 8) -> None:
        font = "hebo" if bold else "helv"
        width = PAGE_W - 2 * MARGIN
        # Estimate height generously; move to a new page if the box would not fit.
        lines = max(1, int(pymupdf.get_text_length(text, fontname=font, fontsize=size) / width) + 1)
        height = lines * size * 1.5 + 4
        if self.cursor.y + height > PAGE_H - 60:
            self.cursor = self._new_page()
        rect = pymupdf.Rect(MARGIN, self.cursor.y, PAGE_W - MARGIN, self.cursor.y + height)
        spare = self.cursor.page.insert_textbox(rect, text, fontsize=size, fontname=font)
        if spare < 0:
            raise RuntimeError("text did not fit; increase the height estimate")
        self.cursor.y += height - spare + gap

    def heading(self, text: str, size: float = 12) -> None:
        self.write(text, size=size, bold=True, gap=4)

    def page_break(self) -> None:
        self.cursor = self._new_page()

    def save(self, path: Path, **kwargs) -> Path:
        self.doc.save(path, **kwargs)
        self.doc.close()
        return path


def write_paper(
    path: Path,
    *,
    footer_start: int | None = 101,
    with_doi: bool = True,
    with_keywords: bool = True,
    page_labels: list[dict] | None = None,
    metadata: dict[str, str] | None = None,
    extra_paragraphs: int = 0,
) -> Path:
    """A three-to-four page synthetic paper with numbered sections."""
    w = PaperWriter(footer_start=footer_start)
    w.write(TITLE, size=18, bold=True, gap=6)
    w.write(AUTHORS, size=11)
    w.write("Department of Examples, Test University", size=9)
    if with_doi:
        w.write(f"DOI: {DOI}    © 2024 The Authors", size=8)
    w.heading("Abstract", size=11)
    w.write(ABSTRACT)
    if with_keywords:
        w.write(KEYWORDS)
    w.heading("1 Introduction")
    for p in INTRO:
        w.write(p)
    w.heading("2 Related Work")
    for p in RELATED:
        w.write(p)
    w.page_break()
    w.heading("3 Methodology")
    for p in METHOD:
        w.write(p)
    w.heading("3.1 Data Preprocessing", size=11)
    for p in METHOD_SUB:
        w.write(p)
    for i in range(extra_paragraphs):
        w.write(
            f"Additional implementation note {i + 1}. The encoder processes passages in "
            "batches and stores normalised vectors. Each vector keeps its chunk identifier "
            "together with the page index and section name for later citation checks."
        )
    w.heading("4 Experiments")
    for p in EXPERIMENTS:
        w.write(p)
    w.heading("5 Results")
    for p in RESULTS:
        w.write(p)
    w.heading("6 Conclusion")
    for p in CONCLUSION:
        w.write(p)
    w.page_break()
    w.heading("References")
    for p in REFERENCES:
        w.write(p, size=9)
    if page_labels:
        w.doc.set_page_labels(page_labels)
    if metadata:
        w.doc.set_metadata(metadata)
    return w.save(path)


def write_plain_pdf(path: Path, paragraphs: list[str], *, pages: int = 1) -> Path:
    """Minimal PDF: plain body text only, no headings, no header/footer."""
    w = PaperWriter(running_header=False, footer_start=None)
    for page in range(pages):
        if page:
            w.page_break()
        for paragraph in paragraphs:
            w.write(paragraph)
    return w.save(path)


def write_scanned_pdf(path: Path, *, pages: int = 1) -> Path:
    """Pages that contain only a raster image of text (no text layer)."""
    source = pymupdf.open()
    page = source.new_page(width=PAGE_W, height=PAGE_H)
    page.insert_textbox(
        pymupdf.Rect(MARGIN, MARGIN, PAGE_W - MARGIN, 400),
        "Scanned page about convolutional networks.",
        fontsize=14,
    )
    pixmap = page.get_pixmap(dpi=72)
    out = pymupdf.open()
    for _ in range(pages):
        target = out.new_page(width=PAGE_W, height=PAGE_H)
        target.insert_image(target.rect, pixmap=pixmap)
    out.save(path)
    out.close()
    source.close()
    return path


def write_mixed_pdf(path: Path) -> Path:
    """A text paper followed by one scanned (image-only) page."""
    paper = pymupdf.open(write_paper(path.with_name(path.stem + "_text.pdf")))
    scanned = pymupdf.open(write_scanned_pdf(path.with_name(path.stem + "_scan.pdf")))
    paper.insert_pdf(scanned)
    paper.save(path)
    paper.close()
    scanned.close()
    return path


def write_blank_pdf(path: Path) -> Path:
    doc = pymupdf.open()
    doc.new_page(width=PAGE_W, height=PAGE_H)
    doc.save(path)
    doc.close()
    return path


def write_encrypted_pdf(path: Path) -> Path:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret")
    doc.save(
        path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner-test", user_pw="user-test"
    )
    doc.close()
    return path


def write_corrupt_pdf(path: Path) -> Path:
    path.write_bytes(b"%PDF-1.7\n1 0 obj << /Type /Catalog >>\n" + b"\x00garbage" * 50)
    return path
