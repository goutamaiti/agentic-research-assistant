"""Regression tests for defects found in the Phase 2 independent review."""

from __future__ import annotations

import threading
from datetime import UTC
from pathlib import Path

import pymupdf
import pytest
from sqlalchemy import select

from app.database.models import Document, DocumentChunk, DocumentStatus, PageExtractionStatus
from app.document_processing.metadata import extract_metadata
from app.document_processing.pdf_parser import find_boilerplate_lines, parse_pdf
from app.document_processing.section_detector import detect_structure
from app.document_processing.types import join_lines
from app.errors import AppError
from app.retrieval import vector_store
from app.retrieval.keyword_search import KeywordIndex, tokenize
from tests.conftest import make_client
from tests.fakes import FakeOcr
from tests.pdf_factory import PaperWriter, write_paper


def _analyse(path: Path):
    parsed = parse_pdf(path, ocr_engine=None)
    boilerplate = find_boilerplate_lines(parsed.pages)
    structure = detect_structure(parsed, boilerplate)
    return parsed, structure, extract_metadata(parsed, structure, boilerplate)


def _upload_and_analyse(client, path: Path) -> str:
    document_id = client.post(
        "/api/documents/upload", files={"file": (path.name, path.read_bytes())}
    ).json()["id"]
    client.post(f"/api/documents/{document_id}/analyze")
    return document_id


# ----- Metadata must come from explicit front-matter evidence only ---------------------


def test_cited_year_and_body_doi_are_not_used_as_paper_metadata(tmp_path: Path) -> None:
    w = PaperWriter(footer_start=None)
    w.write("A Paper Without Its Own DOI Or Copyright Line", size=18, bold=True)
    w.heading("1 Introduction")
    w.write(
        "The BERT model, published in 2019 by Devlin et al., changed NLP. Our dataset is "
        "archived at doi:10.5281/zenodo.1234567 for reproducibility. Figure 1: (a) 2018 "
        "baseline, (b) 2019, (c) 2020 results."
    )
    _, _, metadata = _analyse(w.save(tmp_path / "p.pdf"))
    assert metadata.publication_year.value is None
    assert metadata.publication_year.status == "not_found"
    assert metadata.doi.value is None
    assert metadata.doi.status == "not_found"


def test_labelled_front_matter_doi_and_copyright_year_are_used(tmp_path: Path) -> None:
    _, _, metadata = _analyse(write_paper(tmp_path / "p.pdf"))
    assert metadata.doi.value == "10.5555/sjrt.2024.0042"
    assert metadata.publication_year.value == 2024


@pytest.mark.parametrize(
    ("raw", "status", "value"),
    [
        ("Smith, John; Doe, Jane", "extracted", ["Smith, John", "Doe, Jane"]),
        ("Ada Example and Brian Placeholder", "extracted", ["Ada Example", "Brian Placeholder"]),
        ("A. One, B. Two", "extracted", ["A. One", "B. Two"]),
        ("Smith, John", "ambiguous", ["Smith, John"]),
    ],
)
def test_pdf_metadata_author_splitting(tmp_path: Path, raw: str, status: str, value) -> None:
    path = write_paper(tmp_path / "p.pdf", metadata={"author": raw})
    _, _, metadata = _analyse(path)
    assert metadata.authors.status == status
    assert metadata.authors.value == value


# ----- Page handling ---------------------------------------------------------------------


def test_rotated_page_keeps_numbers_in_body(tmp_path: Path) -> None:
    doc = pymupdf.open()
    for index in range(3):
        page = doc.new_page(width=595, height=842)
        page.insert_text((60, 700), "42", fontsize=10)
        page.insert_text((80, 700), "Mean accuracy over runs", fontsize=10)
        if index == 1:
            page.set_rotation(90)
    path = tmp_path / "rotated.pdf"
    doc.save(path)
    parsed, structure, _ = _analyse(path)
    texts = {p.pdf_page_index: p.text for p in structure.paragraphs}
    assert all("42" in texts[i] for i in range(3)), texts


def test_short_text_page_without_images_is_not_treated_as_scanned(tmp_path: Path) -> None:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 300), "This page is blank.", fontsize=10)
    path = tmp_path / "short.pdf"
    doc.save(path)
    page = parse_pdf(path, ocr_engine=None, ocr_min_text_chars=40).pages[0]
    assert page.extraction_status == PageExtractionStatus.EXTRACTED
    assert page.text == "This page is blank."
    assert page.warnings == []


def test_huge_page_ocr_is_capped_and_never_fails_the_document(tmp_path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=14000, height=14000)  # ~194 x 194 inches
    page.insert_image(
        pymupdf.Rect(0, 0, 100, 100), pixmap=pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 8, 8))
    )
    path = tmp_path / "huge.pdf"
    doc.save(path)
    ocr = FakeOcr()
    parsed = parse_pdf(path, ocr_engine=ocr, ocr_dpi=300)
    assert parsed.pages[0].extraction_status in (
        PageExtractionStatus.OCR_EXTRACTED,
        PageExtractionStatus.OCR_FAILED,
    )


# ----- Text normalisation and keyword search ----------------------------------------------


def test_hyphenated_compound_split_across_lines_is_preserved() -> None:
    assert join_lines(["a state-of-the-", "art model"]) == "a state-of-the-art model"
    assert join_lines(["trans-", "former"]) == "transformer"
    assert join_lines(["COVID-", "19"]) == "COVID-19"


def test_keyword_search_matches_parts_of_compounds() -> None:
    assert {"bert-base", "bert", "base"} <= set(tokenize("BERT-base"))
    assert "5" not in tokenize("3.5")
    index = KeywordIndex(["a", "b"], ["We fine-tune BERT-base with self-attention.", "Tables."])
    assert [hit.chunk_id for hit in index.search("BERT", 5)] == ["a"]
    assert [hit.chunk_id for hit in index.search("attention", 5)] == ["a"]


# ----- Pipeline consistency ----------------------------------------------------------------


def test_concurrent_analyze_requests_queue_only_one_run(settings, monkeypatch) -> None:
    """Two threads pass the 404 check together; the atomic claim admits only one."""
    from app.services import analysis_service as module

    barrier = threading.Barrier(2)
    real_get = module.get_document

    def synchronised_get(session, document_id):
        document = real_get(session, document_id)
        barrier.wait(timeout=5)
        return document

    with make_client(settings) as client:
        path = write_paper(settings.storage_path.parent / "p.pdf")
        document_id = client.post(
            "/api/documents/upload", files={"file": ("p.pdf", path.read_bytes())}
        ).json()["id"]
        service = client.app.state.analysis_service
        submitted: list[str] = []
        service.job_runner.submit = lambda fn, *args: submitted.append(args[1])
        monkeypatch.setattr(module, "get_document", synchronised_get)
        outcomes: list[object] = []

        def attempt() -> None:
            try:
                outcomes.append(service.start(document_id))
            except AppError as exc:
                outcomes.append(exc.code)

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
    assert sorted(str(o) for o in outcomes).count("analysis_in_progress") == 1
    assert len(submitted) == 1


def test_failed_rerun_does_not_leave_stale_index(settings, monkeypatch) -> None:
    with make_client(settings) as client:
        document_id = _upload_and_analyse(
            client, write_paper(settings.storage_path.parent / "p.pdf")
        )
        assert client.get(f"/api/documents/{document_id}").json()["index"]["chunks_indexed"] > 0

        def broken_index(*args, **kwargs):
            raise vector_store.VectorStoreError("disk full")

        monkeypatch.setattr("app.services.analysis_service.index_document", broken_index)
        client.post(f"/api/documents/{document_id}/analyze")
        detail = client.get(f"/api/documents/{document_id}").json()
        with client.app.state.session_factory() as session:
            chunks = session.scalars(
                select(DocumentChunk).where(DocumentChunk.document_id == document_id)
            ).all()
        collections = [c.name for c in client.app.state.chroma_client.list_collections()]
    assert detail["status"] == DocumentStatus.FAILED
    assert detail["index"] == {
        "index_version": None,
        "embedding_model_id": None,
        "chunks_total": 0,
        "chunks_indexed": 0,
    }
    assert chunks == []
    assert f"doc_{document_id}" not in collections


def test_api_timestamps_are_utc_aware(client, tmp_path: Path) -> None:
    path = write_paper(tmp_path / "p.pdf")
    document_id = _upload_and_analyse(client, path)
    detail = client.get(f"/api/documents/{document_id}").json()
    status = client.get(f"/api/documents/{document_id}/status").json()
    assert detail["created_at"].endswith("Z") or detail["created_at"].endswith("+00:00")
    assert status["stages"][0]["started_at"].endswith(("Z", "+00:00"))
    with client.app.state.session_factory() as session:
        assert session.get(Document, document_id).created_at.tzinfo == UTC


def test_upload_commit_failure_leaves_no_orphan_file(settings, monkeypatch) -> None:
    from sqlalchemy.orm import Session

    with make_client(settings) as client:
        path = write_paper(settings.storage_path.parent / "p.pdf")

        def failing_commit(self):
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(Session, "commit", failing_commit)
        # TestClient re-raises server errors; a real client receives a structured 500.
        with pytest.raises(RuntimeError, match="database unavailable"):
            client.post("/api/documents/upload", files={"file": ("p.pdf", path.read_bytes())})
    assert list(settings.uploads_path.iterdir()) == []


# ----- Real-paper layout issues (found with arXiv:1706.03762) -----------------------------


def _latex_like_pdf(path: Path) -> Path:
    """Section numbers and titles as separate fragments, a vertical margin stamp, and a
    label repeated inside figures."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((150, 90), "A Title Set In A Large Font", fontsize=18, fontname="hebo")
    page.insert_text((20, 600), "arXiv:0000.00000v1 [cs.CL] 1 Jan 2030", fontsize=20, rotate=90)
    for y, number, title in ((160, "1", "Introduction"), (300, "2", "Method")):
        page.insert_text((108, y), number, fontsize=12, fontname="hebo")
        page.insert_text((126, y), title, fontsize=12, fontname="hebo")
        page.insert_textbox(
            pymupdf.Rect(108, y + 10, 500, y + 120),
            "Body text of the section that explains the work in plain words. " * 3,
            fontsize=10,
        )
    for y in (500, 650):
        page.insert_text((108, y), "Layer5 Head", fontsize=12, fontname="hebo")
        page.insert_textbox(
            pymupdf.Rect(108, y + 10, 500, y + 60),
            "Caption text describing an attention figure.",
            fontsize=10,
        )
    doc.save(path)
    return path


def test_number_and_title_fragments_form_one_heading(tmp_path: Path) -> None:
    _, structure, metadata = _analyse(_latex_like_pdf(tmp_path / "latex.pdf"))
    titles = [(s.title, s.section_type) for s in structure.sections[1:]]
    assert ("Introduction", "introduction") in titles
    assert ("Method", "methodology") in titles
    assert metadata.title.value == "A Title Set In A Large Font"


def test_vertical_margin_stamp_is_excluded(tmp_path: Path) -> None:
    parsed, structure, _ = _analyse(_latex_like_pdf(tmp_path / "latex.pdf"))
    assert all("arXiv" not in p.text for p in structure.paragraphs)
    assert any("vertical" in w for w in parsed.pages[0].warnings)


def test_repeated_figure_label_is_not_a_heading(tmp_path: Path) -> None:
    _, structure, _ = _analyse(_latex_like_pdf(tmp_path / "latex.pdf"))
    assert all(s.title != "Layer5 Head" for s in structure.sections)
