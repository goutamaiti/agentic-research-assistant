from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.document_processing.chunker import ChunkingConfig, chunk_paragraphs, split_sentences
from app.document_processing.types import Chunk, Paragraph
from app.retrieval.keyword_search import KeywordIndex, tokenize
from app.retrieval.vector_store import (
    VectorRecord,
    VectorStoreError,
    collection_name,
    create_chroma_client,
    delete_document_vectors,
    index_document,
    semantic_search,
)
from tests.fakes import FakeEmbedder


def words(text: str) -> int:
    return len(text.split())


def sentence(i: int) -> str:
    """A distinct ten-word sentence starting with an uppercase letter."""
    return f"Topic{i} " + " ".join(f"w{i}x{j}" for j in range(8)) + " end."


def para(text: str, page: int = 0, section: int = 0) -> Paragraph:
    return Paragraph(text=text, pdf_page_index=page, section_index=section)


CONFIG = ChunkingConfig(target_tokens=25, overlap_tokens=12, max_tokens=40)


# --- chunker ---------------------------------------------------------------------------


def test_split_sentences_respects_abbreviations() -> None:
    text = (
        "We use regularisers, e.g. Dropout and weight decay. "
        "This follows Smith et al. (2020) closely. "
        "Results are in Fig. 3 below. Done!"
    )
    assert split_sentences(text) == [
        "We use regularisers, e.g. Dropout and weight decay.",
        "This follows Smith et al. (2020) closely.",
        "Results are in Fig. 3 below.",
        "Done!",
    ]


def test_paragraph_that_fits_is_not_split() -> None:
    text = " ".join(sentence(i) for i in range(2))  # 20 words <= target 25
    chunks = chunk_paragraphs([para(text, page=4)], CONFIG, words)
    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].token_count == 20
    assert (chunks[0].pdf_page_start, chunks[0].pdf_page_end) == (4, 4)


def test_consecutive_chunks_share_whole_sentence_overlap() -> None:
    sentences = [sentence(i) for i in range(6)]
    chunks = chunk_paragraphs([para(" ".join(sentences))], CONFIG, words)
    assert [c.text for c in chunks] == [f"{sentences[i]} {sentences[i + 1]}" for i in range(5)]
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        assert split_sentences(prev.text)[-1] == split_sentences(nxt.text)[0]
    assert all(c.token_count <= CONFIG.max_tokens for c in chunks)


def test_no_overlap_when_overlap_tokens_is_zero() -> None:
    sentences = [sentence(i) for i in range(6)]
    config = ChunkingConfig(target_tokens=25, overlap_tokens=0, max_tokens=40)
    chunks = chunk_paragraphs([para(" ".join(sentences))], config, words)
    assert [c.text for c in chunks] == [f"{sentences[i]} {sentences[i + 1]}" for i in (0, 2, 4)]
    seen: set[str] = set()
    for chunk in chunks:
        current = set(split_sentences(chunk.text))
        assert not current & seen
        seen |= current


def test_oversized_sentence_split_into_word_windows() -> None:
    long_sentence = "Long " + " ".join(f"tok{i}" for i in range(98)) + " end."  # 100 words
    chunks = chunk_paragraphs([para(long_sentence)], CONFIG, words)
    assert len(chunks) > 1
    assert all(c.token_count <= CONFIG.max_tokens for c in chunks)
    assert all(c.token_count == words(c.text) for c in chunks)
    # Word windows carry no partial-sentence overlap: every word appears exactly once.
    assert " ".join(c.text for c in chunks).split() == long_sentence.split()


def test_chunks_never_cross_sections_and_indices_are_sequential() -> None:
    paragraphs = [
        para(" ".join(sentence(i) for i in range(4)), page=0, section=0),
        para(" ".join(sentence(i) for i in range(10, 15)), page=1, section=1),
        para(sentence(20), page=2, section=2),
    ]
    chunks = chunk_paragraphs(paragraphs, CONFIG, words)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert {c.section_index for c in chunks} == {0, 1, 2}
    owners = {0: range(0, 4), 1: range(10, 15), 2: range(20, 21)}
    for chunk in chunks:
        allowed = {sentence(i) for i in owners[chunk.section_index]}
        assert set(split_sentences(chunk.text)) <= allowed
    # Reading order: section indices never go backwards.
    sections = [c.section_index for c in chunks]
    assert sections == sorted(sections)


def test_page_provenance_spans_pages_within_a_section() -> None:
    paragraphs = [
        para(sentence(1), page=2, section=3),
        para(sentence(2), page=3, section=3),
    ]
    chunks = chunk_paragraphs(paragraphs, CONFIG, words)
    assert len(chunks) == 1
    assert chunks[0].section_index == 3
    assert (chunks[0].pdf_page_start, chunks[0].pdf_page_end) == (2, 3)


def test_page_provenance_across_multiple_chunks() -> None:
    paragraphs = [para(sentence(i), page=10 + i, section=0) for i in range(5)]
    chunks = chunk_paragraphs(paragraphs, CONFIG, words)
    for chunk in chunks:
        pages = [10 + i for i in range(5) if sentence(i) in chunk.text]
        assert (chunk.pdf_page_start, chunk.pdf_page_end) == (min(pages), max(pages))


def test_short_tail_is_merged_into_previous_chunk() -> None:
    first = " ".join(f"a{i}" for i in range(20))
    second = " ".join(f"b{i}" for i in range(24))
    tail = "Short tail here."
    config = ChunkingConfig(target_tokens=25, overlap_tokens=0, max_tokens=40)
    paragraphs = [
        para(first, page=0),
        para(second, page=1),
        para(tail, page=2),
    ]
    chunks = chunk_paragraphs(paragraphs, config, words)
    assert [c.text for c in chunks] == [first, f"{second} {tail}"]
    assert chunks[-1].token_count == 27
    assert (chunks[-1].pdf_page_start, chunks[-1].pdf_page_end) == (1, 2)


def test_invariants_with_embedder_token_counter() -> None:
    count = FakeEmbedder().count_tokens
    config = ChunkingConfig(target_tokens=60, overlap_tokens=15, max_tokens=80)
    paragraphs: list[Paragraph] = []
    for section in range(3):
        for page in range(2):
            text = " ".join(
                f"Section {section}, page {page}, sentence {i}: the model (e.g. BERT) "
                f"was tuned by Lee et al. on data set {i}."
                for i in range(6)
            )
            paragraphs.append(para(text, page=section * 2 + page, section=section))
    chunks: list[Chunk] = chunk_paragraphs(paragraphs, config, count)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    for chunk in chunks:
        assert chunk.token_count == count(chunk.text)
        assert chunk.token_count <= config.max_tokens
        assert chunk.pdf_page_start <= chunk.pdf_page_end
        assert f"Section {chunk.section_index}," in chunk.text
        for other in {0, 1, 2} - {chunk.section_index}:
            assert f"Section {other}," not in chunk.text
    # Provenance of section 0 covers both of its pages.
    sec0 = [c for c in chunks if c.section_index == 0]
    assert sec0[0].pdf_page_start == 0 and sec0[-1].pdf_page_end == 1


# --- keyword search --------------------------------------------------------------------


def test_tokenize_keeps_technical_tokens_and_drops_stopwords() -> None:
    tokens = tokenize("The BERT-base model and GPT-4 reach an F1 of 0.91 with lr 1e-5.")
    for token in ("bert-base", "gpt-4", "f1", "1e-5", "0.91", "model"):
        assert token in tokens
    for stopword in ("the", "and", "an", "of", "with"):
        assert stopword not in tokens


def test_keyword_search_ranks_matching_chunk_first() -> None:
    index = KeywordIndex(
        ["c1", "c2", "c3"],
        [
            "We describe the dataset collection process.",
            "Fine-tuning BERT-base with learning rate 1e-5 gives the best F1.",
            "Related work on convolutional networks.",
        ],
    )
    hits = index.search("BERT-base learning rate", k=3)
    assert [h.chunk_id for h in hits] == ["c2"]
    assert hits[0].score > 0


def test_keyword_search_no_shared_term_or_empty_corpus() -> None:
    index = KeywordIndex(["c1", "c2"], ["alpha beta", "gamma delta"])
    assert index.search("transformer", k=5) == []
    assert index.search("the and of", k=5) == []  # only stopwords
    empty = KeywordIndex([], [])
    assert len(empty) == 0
    assert empty.search("anything", k=5) == []


def test_keyword_search_respects_k() -> None:
    texts = [f"attention layer variant {i}" for i in range(6)]
    index = KeywordIndex([f"c{i}" for i in range(6)], texts)
    assert len(index.search("attention", k=3)) == 3
    assert len(index.search("attention", k=10)) == 6


def test_keyword_index_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError):
        KeywordIndex(["c1"], [])


# --- vector store ----------------------------------------------------------------------


def _doc_id() -> str:
    return uuid.uuid4().hex


def _record(chunk_id: str, embedding: list[float], page: int) -> VectorRecord:
    return VectorRecord(
        chunk_id=chunk_id,
        text=f"text of {chunk_id}",
        embedding=embedding,
        metadata={"pdf_page_index": page, "section_index": 0},
    )


@pytest.mark.parametrize(
    "bad",
    ["", "abc", "A" * 32, "g" * 32, "0" * 31, "0" * 33, "../" + "0" * 29, "0" * 31 + "\n"],
)
def test_collection_name_rejects_invalid_ids(bad: str) -> None:
    with pytest.raises(ValueError):
        collection_name(bad)


def test_collection_name_for_valid_id() -> None:
    doc = "0123456789abcdef" * 2
    assert collection_name(doc) == f"doc_{doc}"


def test_index_replace_search_and_delete(tmp_path: Path) -> None:
    client = create_chroma_client(tmp_path / "chroma")
    doc = _doc_id()
    records = [
        _record("a", [1.0, 0.0, 0.0], 0),
        _record("b", [0.0, 1.0, 0.0], 1),
        _record("c", [0.0, 0.0, 1.0], 2),
    ]
    stored = index_document(client, doc, records, index_version="v1", embedding_model_id="m")
    assert stored == 3
    collection = client.get_collection(collection_name(doc))
    assert collection.metadata["index_version"] == "v1"
    assert collection.metadata["embedding_model_id"] == "m"

    # Cosine space: a scaled copy of a vector is at distance ~0 (L2 would be 1).
    hits = semantic_search(client, doc, [2.0, 0.0, 0.0], k=10)
    assert [h.chunk_id for h in hits][0] == "a"
    assert len(hits) == 3
    assert hits[0].distance == pytest.approx(0.0, abs=1e-5)
    assert hits[1].distance == pytest.approx(1.0, abs=1e-5)
    assert hits[0].text == "text of a"
    assert hits[0].metadata["pdf_page_index"] == 0

    assert len(semantic_search(client, doc, [0.0, 1.0, 0.0], k=1)) == 1
    filtered = semantic_search(client, doc, [1.0, 0.0, 0.0], k=3, where={"pdf_page_index": 2})
    assert [h.chunk_id for h in filtered] == ["c"]

    # Re-indexing replaces the collection rather than appending to it.
    stored = index_document(
        client, doc, [_record("z", [0.0, 1.0, 0.0], 5)], index_version="v2", embedding_model_id="m"
    )
    assert stored == 1
    hits = semantic_search(client, doc, [1.0, 0.0, 0.0], k=5)
    assert [h.chunk_id for h in hits] == ["z"]
    assert client.get_collection(collection_name(doc)).metadata["index_version"] == "v2"

    delete_document_vectors(client, doc)
    delete_document_vectors(client, doc)  # idempotent
    with pytest.raises(VectorStoreError):
        semantic_search(client, doc, [1.0, 0.0, 0.0], k=1)


def test_documents_are_isolated_and_empty_index(tmp_path: Path) -> None:
    client = create_chroma_client(tmp_path / "chroma")
    doc_a, doc_b = _doc_id(), _doc_id()
    index_document(
        client, doc_a, [_record("a1", [1.0, 0.0], 0)], index_version="v1", embedding_model_id="m"
    )
    assert index_document(client, doc_b, [], index_version="v1", embedding_model_id="m") == 0
    assert semantic_search(client, doc_b, [1.0, 0.0], k=3) == []
    assert [h.chunk_id for h in semantic_search(client, doc_a, [1.0, 0.0], k=3)] == ["a1"]
    with pytest.raises(VectorStoreError):
        semantic_search(client, _doc_id(), [1.0, 0.0], k=1)
    with pytest.raises(ValueError):
        index_document(client, "bad", [], index_version="v1", embedding_model_id="m")
