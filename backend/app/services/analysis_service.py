"""Analysis runs: start, execute stages, record status, recover after interruption.

Stages (spec §8.1): upload validation, document extraction, section identification and
retrieval indexing are *fatal* (the run stops and the document is ``failed``); knowledge
extraction is *non-fatal* (the document stays indexed and searchable, and the stage
records why extraction failed or was skipped). Verification is added in Phase 5, and
LangGraph orchestration in Phase 4.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from chromadb.api import ClientAPI
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.agents.extraction_agent import ExtractionAgent
from app.agents.verification_agent import VerificationAgent
from app.config import INDEX_VERSION, Settings
from app.database.models import (
    Document,
    DocumentChunk,
    DocumentPage,
    DocumentSection,
    DocumentStatus,
    Extraction,
    ExtractionRunStatus,
    PageExtractionStatus,
    ProcessingRun,
    RunStatus,
    utcnow,
)
from app.document_processing.chunker import ChunkingConfig, chunk_paragraphs
from app.document_processing.metadata import extract_metadata
from app.document_processing.ocr import OcrEngine
from app.document_processing.pdf_parser import (
    PdfValidationError,
    find_boilerplate_lines,
    parse_pdf,
    validate_pdf,
)
from app.document_processing.section_detector import DocumentStructure, detect_structure
from app.document_processing.types import ParsedDocument
from app.errors import AppError
from app.retrieval.embeddings import Embedder, EmbeddingError
from app.retrieval.keyword_search import KeywordIndex
from app.retrieval.vector_store import (
    VectorRecord,
    VectorStoreError,
    delete_document_vectors,
    index_document,
)
from app.schemas.extraction import ExtractionResult
from app.services.document_service import get_document, resolve_document_file
from app.services.jobs import JobRunner

logger = logging.getLogger(__name__)

STAGES = (
    "upload_validation",
    "document_extraction",
    "section_identification",
    "retrieval_indexing",
    "knowledge_extraction",
    "evidence_verification",
)
# Stages whose failure or interruption leaves the document indexed and searchable.
NON_FATAL_STAGES = ("knowledge_extraction", "evidence_verification")
ACTIVE_STATUSES = (DocumentStatus.QUEUED, DocumentStatus.PROCESSING)
# Sections that are kept and chunked but not embedded unless configured otherwise.
NON_INDEXED_SECTION_TYPES = frozenset({"references", "acknowledgments"})
_UNREADABLE = (PageExtractionStatus.OCR_FAILED, PageExtractionStatus.OCR_UNAVAILABLE)


class StageFailure(Exception):
    """A stage could not complete; ``code`` is stored and shown to the user."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(slots=True)
class StageOutcome:
    status: RunStatus = RunStatus.COMPLETED
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class _RunContext:
    document_id: str
    workflow_run_id: str
    parsed: ParsedDocument | None = None
    structure: DocumentStructure | None = None
    boilerplate: set[str] = field(default_factory=set)
    partial_reasons: list[str] = field(default_factory=list)
    extraction: str | None = None  # completed | partial | failed | skipped
    extraction_detail: str | None = None
    extraction_id: int | None = None  # the Extraction row written by this run


class AnalysisService:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        chroma_client: ClientAPI,
        embedder: Embedder,
        ocr_engine: OcrEngine | None,
        job_runner: JobRunner,
        extraction_agent: ExtractionAgent | None = None,
        verification_agent: VerificationAgent | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.chroma_client = chroma_client
        self.embedder = embedder
        self.ocr_engine = ocr_engine
        self.job_runner = job_runner
        self.extraction_agent = extraction_agent
        self.verification_agent = verification_agent

    # ----- Public API -------------------------------------------------------------------

    def start(self, document_id: str) -> str:
        """Record a new run with all stages pending, queue it, and return its id."""
        with self.session_factory() as session:
            get_document(session, document_id)  # 404 if unknown
            # Atomic claim: of two concurrent requests, only one can move the document
            # out of a non-active status, so a document never has two runs queued.
            claimed = session.execute(
                update(Document)
                .where(Document.id == document_id, Document.status.not_in(ACTIVE_STATUSES))
                .values(
                    status=DocumentStatus.QUEUED,
                    status_detail="Analysis queued.",
                    updated_at=utcnow(),
                )
            )
            if claimed.rowcount != 1:
                session.rollback()
                raise AppError(
                    409,
                    "analysis_in_progress",
                    "An analysis of this document is already queued or running.",
                )
            run_id = uuid.uuid4().hex
            for stage in STAGES:
                session.add(
                    ProcessingRun(
                        document_id=document_id,
                        workflow_run_id=run_id,
                        stage=stage,
                        status=RunStatus.PENDING,
                    )
                )
            session.commit()
        logger.info("Queued analysis run %s for document %s", run_id, document_id)
        self.job_runner.submit(self.run, document_id, run_id)
        return run_id

    def recover(self) -> int:
        """Handle runs left unfinished by a previous process.

        Unfinished stages are marked ``interrupted``. If a processing stage was interrupted,
        the document is ``failed`` and partial results are removed, exactly as for a failed
        stage. If only knowledge extraction was interrupted, the index is complete, so the
        document stays indexed (and searchable) with an explanation.
        """
        first_stale: dict[str, tuple[str, str]] = {}  # document -> (run id, earliest stage)
        with self.session_factory() as session:
            stale = session.scalars(
                select(ProcessingRun).where(
                    ProcessingRun.status.in_([RunStatus.PENDING, RunStatus.RUNNING])
                )
            ).all()
            for run in stale:
                run.status = RunStatus.INTERRUPTED
                run.completed_at = utcnow()
                run.error_json = {
                    "code": "interrupted",
                    "message": "The application stopped before this stage finished.",
                }
                if run.stage in STAGES:
                    known = first_stale.get(run.document_id)
                    if known is None or STAGES.index(run.stage) < STAGES.index(known[1]):
                        first_stale[run.document_id] = (run.workflow_run_id, run.stage)
            session.commit()

        for document_id, (run_id, stage) in first_stale.items():
            if stage in NON_FATAL_STAGES:
                self._set_document(document_id, *self._status_after_interrupted_extraction(run_id))
            else:
                self._discard_stale_results(document_id, failed_stage=stage)
                self._set_document(
                    document_id,
                    DocumentStatus.FAILED,
                    f"Analysis was interrupted during {stage.replace('_', ' ')}. "
                    "Start the analysis again.",
                )

        # Any other document left in an active state has no usable run.
        with self.session_factory() as session:
            session.execute(
                update(Document)
                .where(Document.status.in_(ACTIVE_STATUSES))
                .values(
                    status=DocumentStatus.FAILED,
                    status_detail="Analysis was interrupted. Start the analysis again.",
                    updated_at=utcnow(),
                )
            )
            session.commit()
        if stale:
            logger.warning("Marked %d unfinished stage(s) as interrupted", len(stale))
        return len(stale)

    def _status_after_interrupted_extraction(self, run_id: str) -> tuple[DocumentStatus, str]:
        with self.session_factory() as session:
            extraction_stage = session.scalar(
                select(ProcessingRun).where(
                    ProcessingRun.workflow_run_id == run_id,
                    ProcessingRun.stage == "document_extraction",
                )
            )
            partial = extraction_stage is not None and extraction_stage.status == RunStatus.PARTIAL
        detail = (
            "Knowledge extraction was interrupted; start the analysis again to extract "
            "structured knowledge."
        )
        if partial:
            return DocumentStatus.PARTIALLY_INDEXED, f"Indexed with limitations. {detail}"
        return DocumentStatus.INDEXED, f"Document indexed. {detail}"

    def run(self, document_id: str, workflow_run_id: str) -> None:
        """Execute all stages of one run. Never raises: failures are recorded."""
        from app.workflows.analysis_graph import build_analysis_graph

        context = _RunContext(document_id=document_id, workflow_run_id=workflow_run_id)
        self._set_document(document_id, DocumentStatus.PROCESSING, "Processing document.")
        graph = build_analysis_graph(self, context)
        final = graph.invoke(
            {
                "document_id": document_id,
                "workflow_run_id": workflow_run_id,
                "processing_status": "running",
                "processing_errors": [],
                "completed_stages": [],
            }
        )
        logger.info(
            "Run %s ended (%s) for document %s",
            workflow_run_id,
            final.get("processing_status"),
            document_id,
        )

    # ----- Graph node bodies --------------------------------------------------------------

    def execute_processing_stage(self, context: _RunContext, stage: str) -> dict[str, str] | None:
        """Run one fatal stage. On failure, record it, skip later stages, discard stale
        results, mark the document failed, and return the error."""
        functions: dict[str, Callable[[_RunContext], StageOutcome]] = {
            "upload_validation": self._stage_upload_validation,
            "document_extraction": self._stage_document_extraction,
            "section_identification": self._stage_section_identification,
            "retrieval_indexing": self._stage_retrieval_indexing,
        }
        self._update_stage(context, stage, status=RunStatus.RUNNING, started=True)
        started = time.perf_counter()
        try:
            outcome = functions[stage](context)
        except Exception as exc:
            error = self._describe_error(exc)
            logger.error(
                "Run %s stage %s failed: %s",
                context.workflow_run_id,
                stage,
                error["code"],
                exc_info=not isinstance(exc, StageFailure | PdfValidationError),
            )
            self._update_stage(
                context,
                stage,
                status=RunStatus.FAILED,
                completed=True,
                error=error,
                metrics={"duration_ms": _elapsed_ms(started)},
            )
            for skipped in STAGES[STAGES.index(stage) + 1 :]:
                self._update_stage(context, skipped, status=RunStatus.SKIPPED)
            self._discard_stale_results(context.document_id, failed_stage=stage)
            self._set_document(
                context.document_id,
                DocumentStatus.FAILED,
                f"{stage.replace('_', ' ').capitalize()} failed: {error['message']}",
            )
            return error
        outcome.metrics["duration_ms"] = _elapsed_ms(started)
        self._update_stage(
            context, stage, status=outcome.status, completed=True, metrics=outcome.metrics
        )
        return None

    def execute_extraction_stage(self, context: _RunContext) -> None:
        self._run_extraction_stage(context)

    def execute_verification_stage(self, context: _RunContext) -> None:
        """Verify this run's claims and store the verified analysis. Non-fatal."""
        from app.agents.verification_agent import PROMPT_VERSION as VERIFY_PROMPT

        stage = "evidence_verification"
        self._update_stage(context, stage, status=RunStatus.RUNNING, started=True)
        started = time.perf_counter()
        if context.extraction_id is None or self.verification_agent is None:
            self._update_stage(
                context,
                stage,
                status=RunStatus.SKIPPED,
                completed=True,
                metrics={"reason": "no_analysis_to_verify"},
            )
            return
        try:
            with self.session_factory() as session:
                row = session.get(Extraction, context.extraction_id)
                result = ExtractionResult.model_validate(row.result_json)
                verified = self.verification_agent.verify(result)
                row.result_json = verified.model_dump(mode="json")
                session.commit()
        except Exception as exc:
            error = self._describe_error(exc)
            logger.error(
                "Run %s verification failed: %s",
                context.workflow_run_id,
                error["code"],
                exc_info=True,
            )
            self._update_stage(
                context,
                stage,
                status=RunStatus.FAILED,
                completed=True,
                error=error,
                metrics={"duration_ms": _elapsed_ms(started)},
            )
            return
        self._update_stage(
            context,
            stage,
            status=RunStatus.COMPLETED,
            completed=True,
            metrics={
                "verification_summary": verified.processing_metadata.verification_summary,
                "llm_used": self.verification_agent.llm is not None,
                "prompt_version": VERIFY_PROMPT,
                "duration_ms": _elapsed_ms(started),
            },
        )

    def finalize_run(self, context: _RunContext) -> None:
        self._set_document(context.document_id, *self._final_status(context))

    def _run_extraction_stage(self, context: _RunContext) -> None:
        """Run knowledge extraction; failures are recorded but never fail the document."""
        stage = "knowledge_extraction"
        self._update_stage(context, stage, status=RunStatus.RUNNING, started=True)
        started = time.perf_counter()
        try:
            outcome = self._stage_knowledge_extraction(context)
        except Exception as exc:
            error = self._describe_error(exc)
            logger.error(
                "Run %s knowledge extraction failed: %s",
                context.workflow_run_id,
                error["code"],
                exc_info=True,
            )
            context.extraction, context.extraction_detail = "failed", error["message"]
            self._update_stage(
                context,
                stage,
                status=RunStatus.FAILED,
                completed=True,
                error=error,
                metrics={"duration_ms": _elapsed_ms(started)},
            )
            return
        outcome.metrics["duration_ms"] = _elapsed_ms(started)
        self._update_stage(
            context, stage, status=outcome.status, completed=True, metrics=outcome.metrics
        )

    @staticmethod
    def _final_status(context: _RunContext) -> tuple[DocumentStatus, str]:
        limitations = list(context.partial_reasons)
        if context.extraction in ("completed", "partial"):
            if context.extraction == "partial":
                limitations.append(context.extraction_detail or "some extraction tasks failed")
            if limitations:
                return (
                    DocumentStatus.PARTIALLY_ANALYZED,
                    "Analysed with limitations: " + "; ".join(limitations),
                )
            return DocumentStatus.ANALYZED, "Document indexed and analysed."
        prefix = {
            "skipped": "Knowledge extraction skipped",
            "failed": "Knowledge extraction failed",
        }.get(context.extraction or "", "Knowledge extraction not run")
        detail = f"{prefix}: {context.extraction_detail or 'no details'}."
        if limitations:
            return (
                DocumentStatus.PARTIALLY_INDEXED,
                "Indexed with limitations: " + "; ".join(limitations) + ". " + detail,
            )
        return DocumentStatus.INDEXED, f"Document indexed. {detail}"

    # ----- Stages -----------------------------------------------------------------------

    def _stage_upload_validation(self, context: _RunContext) -> StageOutcome:
        with self.session_factory() as session:
            document = get_document(session, context.document_id)
            path = resolve_document_file(self.settings, document)
            expected_sha = document.sha256
        if not path.is_file():
            raise StageFailure("file_missing", "The stored PDF file is missing.")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != expected_sha:
            raise StageFailure(
                "file_changed", "The stored PDF no longer matches the uploaded file."
            )
        info = validate_pdf(path)
        return StageOutcome(
            metrics={"page_count": info.page_count, "file_size": path.stat().st_size}
        )

    def _stage_document_extraction(self, context: _RunContext) -> StageOutcome:
        with self.session_factory() as session:
            path = resolve_document_file(self.settings, get_document(session, context.document_id))
        parsed = parse_pdf(
            path,
            ocr_engine=self.ocr_engine,
            ocr_min_text_chars=self.settings.ocr_min_text_chars,
            ocr_dpi=self.settings.ocr_dpi,
        )
        context.parsed = parsed
        with self.session_factory() as session:
            session.execute(
                delete(DocumentPage).where(DocumentPage.document_id == context.document_id)
            )
            for page in parsed.pages:
                text = page.text
                session.add(
                    DocumentPage(
                        document_id=context.document_id,
                        pdf_page_index=page.pdf_page_index,
                        displayed_page_number=page.displayed_page_number,
                        page_text=text,
                        ocr_used=page.ocr_used,
                        extraction_status=page.extraction_status,
                        char_count=len(text),
                    )
                )
            document = get_document(session, context.document_id)
            document.page_count = parsed.page_count
            session.commit()

        unreadable = [p.pdf_page_index for p in parsed.pages if p.extraction_status in _UNREADABLE]
        metrics: dict[str, Any] = {
            "page_count": parsed.page_count,
            "text_layer_pages": sum(
                p.extraction_status == PageExtractionStatus.EXTRACTED for p in parsed.pages
            ),
            "ocr_pages": [p.pdf_page_index for p in parsed.pages if p.ocr_used],
            "unreadable_pages": unreadable,
            "empty_pages": [
                p.pdf_page_index
                for p in parsed.pages
                if p.extraction_status == PageExtractionStatus.EMPTY
            ],
            "pages_with_displayed_number": sum(
                p.displayed_page_number is not None for p in parsed.pages
            ),
            "ocr_available": bool(self.ocr_engine and self.ocr_engine.is_available()),
            "warnings": parsed.warnings,
        }
        if not any(p.text.strip() for p in parsed.pages):
            hint = "" if metrics["ocr_available"] else " OCR (Tesseract) is not installed."
            raise StageFailure(
                "no_extractable_text", f"No text could be extracted from the PDF.{hint}"
            )
        if unreadable:
            context.partial_reasons.append(
                f"{len(unreadable)} page(s) could not be read"
                + ("" if metrics["ocr_available"] else " (OCR not installed)")
            )
            return StageOutcome(status=RunStatus.PARTIAL, metrics=metrics)
        return StageOutcome(metrics=metrics)

    def _stage_section_identification(self, context: _RunContext) -> StageOutcome:
        parsed = _require(context.parsed)
        context.boilerplate = find_boilerplate_lines(parsed.pages)
        structure = detect_structure(parsed, context.boilerplate)
        context.structure = structure
        metadata = extract_metadata(parsed, structure, context.boilerplate)

        with self.session_factory() as session:
            session.execute(
                delete(DocumentSection).where(DocumentSection.document_id == context.document_id)
            )
            for section in structure.sections:
                session.add(
                    DocumentSection(
                        document_id=context.document_id,
                        section_index=section.section_index,
                        title=section.title,
                        level=section.level,
                        section_type=section.section_type,
                        parent_index=section.parent_index,
                        start_page_index=section.start_page_index,
                        end_page_index=section.end_page_index,
                    )
                )
            document = get_document(session, context.document_id)
            document.title = metadata.title.value
            document.authors_json = metadata.authors.value or []
            document.publication_year = metadata.publication_year.value
            document.doi = metadata.doi.value
            document.metadata_json = metadata.model_dump(mode="json")
            session.commit()

        warnings = []
        if len(structure.sections) <= 1:
            warnings.append("No section headings were identified; text is kept as one section.")
        return StageOutcome(
            metrics={
                "sections": len(structure.sections) - 1,  # excluding implicit front matter
                "section_types": sorted({s.section_type for s in structure.sections[1:]}),
                "paragraphs": len(structure.paragraphs),
                "body_font_size": structure.body_font_size,
                "boilerplate_lines": len(context.boilerplate),
                "metadata_status": {
                    name: getattr(metadata, name).status.value
                    for name in (
                        "title",
                        "authors",
                        "publication_year",
                        "doi",
                        "abstract",
                        "keywords",
                        "document_language",
                    )
                },
                "warnings": warnings,
            }
        )

    def _stage_retrieval_indexing(self, context: _RunContext) -> StageOutcome:
        parsed = _require(context.parsed)
        structure = _require(context.structure)
        config = ChunkingConfig(
            target_tokens=self.settings.chunk_target_tokens,
            overlap_tokens=self.settings.chunk_overlap_tokens,
            max_tokens=self.settings.chunk_max_tokens,
        )
        try:
            chunks = chunk_paragraphs(structure.paragraphs, config, self.embedder.count_tokens)
            max_seq = self.embedder.max_seq_length
        except EmbeddingError as exc:
            raise StageFailure("embedding_model_unavailable", str(exc)) from exc

        displayed = {p.pdf_page_index: p.displayed_page_number for p in parsed.pages}
        sections = {s.section_index: s for s in structure.sections}
        skip_types = set() if self.settings.index_references else NON_INDEXED_SECTION_TYPES

        rows: list[DocumentChunk] = []
        records_text: list[str] = []
        for chunk in chunks:
            section = sections[chunk.section_index]
            indexed = section.section_type not in skip_types
            row = DocumentChunk(
                document_id=context.document_id,
                chunk_id=f"{context.document_id}_c{chunk.chunk_index:04d}",
                chunk_index=chunk.chunk_index,
                section_index=chunk.section_index,
                section_name=section.title,
                section_type=section.section_type,
                pdf_page_start=chunk.pdf_page_start,
                pdf_page_end=chunk.pdf_page_end,
                displayed_page_start=displayed.get(chunk.pdf_page_start),
                displayed_page_end=displayed.get(chunk.pdf_page_end),
                text=chunk.text,
                token_count=chunk.token_count,
                indexed=indexed,
                index_version=INDEX_VERSION,
            )
            rows.append(row)
            if indexed:
                # The section title gives the embedding context; stored text stays verbatim.
                # The prefix is dropped if it would push the input past the model's limit
                # (2 tokens are reserved for the model's special tokens).
                prefixed = f"{section.title}\n{chunk.text}"
                fits = self.embedder.count_tokens(prefixed) <= max_seq - 2
                records_text.append(prefixed if fits else chunk.text)

        indexed_rows = [row for row in rows if row.indexed]
        over_limit = sum(row.token_count > max_seq - 2 for row in indexed_rows)
        if not indexed_rows:
            raise StageFailure("no_indexable_text", "No indexable text was found in the PDF.")

        try:
            embeddings = self.embedder.embed_documents(records_text)
        except EmbeddingError as exc:
            raise StageFailure("embedding_failed", str(exc)) from exc

        records = [
            VectorRecord(
                chunk_id=row.chunk_id,
                text=row.text,
                embedding=vector,
                metadata=_vector_metadata(row),
            )
            for row, vector in zip(indexed_rows, embeddings, strict=True)
        ]
        try:
            stored = index_document(
                self.chroma_client,
                context.document_id,
                records,
                index_version=INDEX_VERSION,
                embedding_model_id=self.embedder.model_id,
            )
        except VectorStoreError as exc:
            raise StageFailure("vector_indexing_failed", str(exc)) from exc
        if stored != len(records):
            raise StageFailure(
                "vector_index_incomplete",
                f"The vector index holds {stored} of {len(records)} chunks.",
            )

        keyword_index = KeywordIndex(
            [r.chunk_id for r in indexed_rows], [_keyword_text(r) for r in indexed_rows]
        )

        with self.session_factory() as session:
            session.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == context.document_id)
            )
            # Analyses of a previous index cite chunks that are being replaced.
            session.execute(delete(Extraction).where(Extraction.document_id == context.document_id))
            session.add_all(rows)
            document = get_document(session, context.document_id)
            document.index_version = INDEX_VERSION
            document.embedding_model_id = self.embedder.model_id
            session.commit()

        token_counts = [row.token_count for row in rows]
        return StageOutcome(
            metrics={
                "chunks_total": len(rows),
                "chunks_indexed": len(indexed_rows),
                "vectors_stored": stored,
                "keyword_index_size": len(keyword_index),
                "tokens_mean": round(sum(token_counts) / len(token_counts), 1),
                "tokens_max": max(token_counts),
                "embedding_max_seq_length": max_seq,
                # Chunks the model will truncate when embedding (should be 0).
                "chunks_over_model_limit": over_limit,
                "embedding_model_id": self.embedder.model_id,
                "index_version": INDEX_VERSION,
                "chunking": {
                    "target_tokens": config.target_tokens,
                    "overlap_tokens": config.overlap_tokens,
                    "max_tokens": config.max_tokens,
                },
            }
        )

    def _stage_knowledge_extraction(self, context: _RunContext) -> StageOutcome:
        if self.extraction_agent is None:
            context.extraction = "skipped"
            context.extraction_detail = "no Gemini API key is configured (GEMINI_API_KEY)"
            return StageOutcome(status=RunStatus.SKIPPED, metrics={"reason": "llm_not_configured"})
        result = self.extraction_agent.extract(context.document_id, context.workflow_run_id)
        meta = result.processing_metadata
        status = ExtractionRunStatus(meta.processing_status)
        with self.session_factory() as session:
            row = Extraction(
                document_id=context.document_id,
                workflow_run_id=context.workflow_run_id,
                schema_version=result.schema_version,
                model_id=meta.model_id,
                prompt_version=meta.prompt_version,
                embedding_model_id=meta.embedding_model_id,
                index_version=meta.index_version,
                result_json=result.model_dump(mode="json"),
                status=status,
            )
            session.add(row)
            session.commit()
            context.extraction_id = row.id

        context.extraction = status.value
        failed_tasks = [t.task for t in meta.tasks if t.task_status == "failed"]
        if status == ExtractionRunStatus.FAILED:
            context.extraction_detail = "every extraction task failed; see stage metrics"
        elif failed_tasks:
            context.extraction_detail = "extraction task(s) failed: " + ", ".join(failed_tasks)
        matches: dict[str, int] = {}
        for record in result.evidence_registry:
            matches[record.quote_match.value] = matches.get(record.quote_match.value, 0) + 1
        metrics: dict[str, Any] = {
            "model_id": meta.model_id,
            "prompt_version": meta.prompt_version,
            "schema_version": result.schema_version,
            "tasks": [t.model_dump(exclude_none=True) for t in meta.tasks],
            "llm_calls": sum(t.attempts for t in meta.tasks),
            "input_tokens": sum(t.input_tokens or 0 for t in meta.tasks),
            "output_tokens": sum(t.output_tokens or 0 for t in meta.tasks),
            "claims": len(result.claims),
            "evidence_records": len(result.evidence_registry),
            "evidence_quote_match": matches,
            "warnings": meta.warnings,
        }
        run_status = {
            ExtractionRunStatus.COMPLETED: RunStatus.COMPLETED,
            ExtractionRunStatus.PARTIAL: RunStatus.PARTIAL,
            ExtractionRunStatus.FAILED: RunStatus.FAILED,
        }[status]
        return StageOutcome(status=run_status, metrics=metrics)

    # ----- Persistence helpers -----------------------------------------------------------

    def _discard_stale_results(self, document_id: str, *, failed_stage: str) -> None:
        """After a failed run, remove results that could be mistaken for a current index.

        Results written by stages of *this* run before the failure are kept (they are
        accurate diagnostics); anything the failed or later stages would have replaced is
        removed, and the vector index is always dropped, so a failed document never shows
        chunks or vectors from an earlier run.
        """
        order = STAGES.index(failed_stage)
        try:
            delete_document_vectors(self.chroma_client, document_id)
        except Exception:
            logger.exception("Could not remove vectors of failed document %s", document_id)
        with self.session_factory() as session:
            session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
            session.execute(delete(Extraction).where(Extraction.document_id == document_id))
            if order <= STAGES.index("section_identification"):
                session.execute(
                    delete(DocumentSection).where(DocumentSection.document_id == document_id)
                )
            if order <= STAGES.index("document_extraction"):
                session.execute(delete(DocumentPage).where(DocumentPage.document_id == document_id))
            document = session.get(Document, document_id)
            if document is not None:
                document.index_version = None
                document.embedding_model_id = None
                if order <= STAGES.index("section_identification"):
                    document.metadata_json = None
                    document.title = None
                    document.authors_json = []
                    document.publication_year = None
                    document.doi = None
            session.commit()

    def _set_document(self, document_id: str, status: DocumentStatus, detail: str) -> None:
        with self.session_factory() as session:
            document = session.get(Document, document_id)
            if document is not None:
                document.status = status
                document.status_detail = detail
                session.commit()

    def _update_stage(
        self,
        context: _RunContext,
        stage: str,
        *,
        status: RunStatus,
        started: bool = False,
        completed: bool = False,
        error: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        with self.session_factory() as session:
            run = session.scalar(
                select(ProcessingRun).where(
                    ProcessingRun.workflow_run_id == context.workflow_run_id,
                    ProcessingRun.stage == stage,
                )
            )
            if run is None:  # e.g. the document was deleted mid-run
                return
            run.status = status
            if started:
                run.started_at = utcnow()
            if completed:
                run.completed_at = utcnow()
            if error is not None:
                run.error_json = error
            if metrics is not None:
                run.metrics_json = metrics
            session.commit()

    @staticmethod
    def _describe_error(exc: Exception) -> dict[str, str]:
        if isinstance(exc, StageFailure):
            return {"code": exc.code, "message": exc.message}
        if isinstance(exc, PdfValidationError):
            return {"code": exc.code, "message": exc.message}
        if isinstance(exc, AppError):
            return {"code": exc.code, "message": exc.message}
        return {
            "code": "internal_error",
            "message": f"Unexpected error ({type(exc).__name__}). See server logs.",
        }


def latest_run(session: Session, document_id: str) -> tuple[str | None, list[ProcessingRun]]:
    run_id = session.scalar(
        select(ProcessingRun.workflow_run_id)
        .where(ProcessingRun.document_id == document_id)
        .order_by(ProcessingRun.id.desc())
        .limit(1)
    )
    if run_id is None:
        return None, []
    stages = session.scalars(
        select(ProcessingRun)
        .where(ProcessingRun.workflow_run_id == run_id)
        .order_by(ProcessingRun.id)
    ).all()
    return run_id, list(stages)


def _vector_metadata(row: DocumentChunk) -> dict[str, str | int | float | bool]:
    # Chroma metadata values cannot be None; unknown values are omitted.
    metadata: dict[str, str | int | float | bool] = {
        "document_id": row.document_id,
        "chunk_id": row.chunk_id,
        "chunk_index": row.chunk_index,
        "pdf_page_index": row.pdf_page_start,
        "pdf_page_end": row.pdf_page_end,
        "section_type": row.section_type or "other",
        "index_version": row.index_version,
    }
    if row.section_name:
        metadata["section_name"] = row.section_name
    if row.displayed_page_start:
        metadata["displayed_page_number"] = row.displayed_page_start
    return metadata


def _keyword_text(row: DocumentChunk) -> str:
    return f"{row.section_name or ''}\n{row.text}"


def _require[T](value: T | None) -> T:
    if value is None:
        raise StageFailure("missing_stage_input", "A previous stage produced no output.")
    return value


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
