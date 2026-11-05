"""Knowledge Extraction Agent (spec §7.4).

For one indexed document it runs a small, fixed set of extraction tasks. Each task:
1. selects relevant passages deterministically (chunks from matching sections, plus
   semantic and keyword hits for task-specific queries), within a token budget;
2. makes one structured LLM call with a task-specific prompt and response schema;
3. has its output turned into claims and evidence records by ``ResultAssembler``.

A failed task marks only its own categories as failed (``task_status``); the other
categories are still extracted (spec §8.1: a missing category must not fail the paper).
There is no open-ended agent loop: the task list is fixed and each call is bounded by the
LLM service's retry limits.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from chromadb.api import ClientAPI
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import Document, DocumentChunk, DocumentPage
from app.prompts.extraction import (
    METADATA,
    PROMPT_VERSION,
    SYSTEM_INSTRUCTION,
    TASK_PROMPTS,
    PromptPassage,
    TaskPrompt,
    build_prompt,
)
from app.retrieval.embeddings import Embedder
from app.retrieval.keyword_search import KeywordIndex
from app.retrieval.vector_store import VectorStoreError, semantic_search
from app.schemas.evidence import Claim, ClaimCategory, EvidenceRecord, Origin, QuoteMatch
from app.schemas.extraction import (
    CategoryBase,
    ExperimentsTaskResponse,
    ExtractionResult,
    Grounded,
    MetadataResponse,
    MetadataValue,
    MethodsTaskResponse,
    OverviewTaskResponse,
    PaperMetadata,
    ProcessingMetadata,
    TaskRecord,
    TextField,
)
from app.schemas.paper import DocumentMetadata, ExtractionStatus
from app.services.evidence_linker import EvidenceLinker, PassageSource
from app.services.llm_service import LLMError, LLMService

logger = logging.getLogger(__name__)

_ABBREVIATION = re.compile(r"\(([A-Z][A-Za-z0-9-]*[A-Z0-9])s?\)")


@dataclass(frozen=True, slots=True)
class ExtractionTask:
    prompt: TaskPrompt
    response_model: type[BaseModel]
    section_types: tuple[str, ...]
    queries: tuple[str, ...]
    # Where each response field goes in the final result: field -> (part, category path).
    targets: dict[str, tuple[str, str]] = field(default_factory=dict)
    includes_metadata: bool = False  # front-matter passages + publication metadata
    includes_terminology: bool = False  # passages that define abbreviations


def _merged(name: str, *prompts: TaskPrompt) -> TaskPrompt:
    return TaskPrompt(name, "\n".join(p.instructions for p in prompts))


# Three calls per paper (run in parallel), each covering related categories.
TASKS: tuple[ExtractionTask, ...] = (
    ExtractionTask(
        _merged("overview", TASK_PROMPTS["overview"], METADATA),
        OverviewTaskResponse,
        ("abstract", "introduction", "related_work"),
        (
            "research problem addressed by this paper",
            "objectives and aims of this work",
            "motivation and shortcomings of existing approaches",
            "prior work and related approaches",
        ),
        {
            name: ("research_analysis", name)
            for name in ("abstract", "research_problem", "objectives", "motivation", "background")
        },
        includes_metadata=True,
    ),
    ExtractionTask(
        _merged("methods", TASK_PROMPTS["methods"], TASK_PROMPTS["terminology"]),
        MethodsTaskResponse,
        ("methodology",),
        (
            "proposed method and architecture",
            "algorithm procedure and steps",
            "model configuration and hyperparameters",
            "definition of a technical term",
        ),
        {
            "methodology": ("research_analysis", "methodology"),
            "algorithms_and_models": ("technical_analysis", "algorithms_and_models"),
            "methodology_breakdown": ("technical_analysis", "methodology_breakdown"),
            "technical_terminology": ("technical_analysis", "technical_terminology"),
        },
        includes_terminology=True,
    ),
    ExtractionTask(
        _merged("experiments", TASK_PROMPTS["experiments"], TASK_PROMPTS["outlook"]),
        ExperimentsTaskResponse,
        ("experiments", "results", "conclusion", "discussion", "limitations", "future_work"),
        (
            "datasets used for training and evaluation",
            "experimental setup hardware and training",
            "evaluation metrics and results compared with baselines",
            "limitations of this work",
            "future work and directions",
            "the main contributions of this paper",
        ),
        {
            "dataset_and_experiments": ("technical_analysis", "dataset_and_experiments"),
            "results": ("research_analysis", "results"),
            "limitations": ("research_analysis", "limitations"),
            "future_scope": ("research_analysis", "future_scope"),
            "research_contributions": ("technical_analysis", "research_contributions"),
        },
    ),
)

# Claim category for a response field (and sub-field, when it differs).
_CATEGORY: dict[str, ClaimCategory] = {
    "abstract": "abstract",
    "research_problem": "research_problem",
    "objectives": "objective",
    "motivation": "motivation",
    "background": "background",
    "methodology": "methodology",
    "algorithms_and_models": "algorithm",
    "methodology_breakdown": "methodology_step",
    "dataset_and_experiments": "experimental_setup",
    "results": "result",
    "limitations": "limitation",
    "future_scope": "future_scope",
    "research_contributions": "contribution",
    "technical_terminology": "terminology",
}
_INFERRED_LISTS = frozenset({"system_inferred", "system_suggested"})
_AUTHOR_LISTS = frozenset({"author_acknowledged", "author_proposed", "author_claimed"})


# ----- Passage selection ---------------------------------------------------------------


@dataclass(slots=True)
class _Chunk:
    chunk_id: str
    chunk_index: int
    text: str
    section_name: str | None
    section_type: str | None
    pdf_page_start: int
    pdf_page_end: int
    displayed_page_start: str | None
    token_count: int
    indexed: bool


def _page_label(chunk: _Chunk) -> str:
    label = f"pdf-index {chunk.pdf_page_start}"
    if chunk.pdf_page_end != chunk.pdf_page_start:
        label += f"-{chunk.pdf_page_end}"
    if chunk.displayed_page_start:
        label += f", printed {chunk.displayed_page_start}"
    return label


class PassageSelector:
    def __init__(
        self,
        chunks: list[_Chunk],
        *,
        document_id: str,
        chroma_client: ClientAPI,
        embedder: Embedder,
        token_budget: int,
        candidates: int,
    ) -> None:
        self._chunks = chunks
        self._by_id = {c.chunk_id: c for c in chunks}
        self._document_id = document_id
        self._chroma = chroma_client
        self._embedder = embedder
        self._budget = token_budget
        self._k = candidates
        searchable = [c for c in chunks if c.indexed]
        self._keyword = KeywordIndex(
            [c.chunk_id for c in searchable],
            [f"{c.section_name or ''}\n{c.text}" for c in searchable],
        )

    def _retrieved(self, query: str) -> list[str]:
        ids: list[str] = []
        try:
            hits = semantic_search(
                self._chroma, self._document_id, self._embedder.embed_query(query), self._k
            )
            ids.extend(h.chunk_id for h in hits)
        except VectorStoreError:
            logger.warning("Semantic search failed during extraction; using keyword hits only")
        ids.extend(h.chunk_id for h in self._keyword.search(query, self._k))
        return ids

    def select(self, task: ExtractionTask) -> list[_Chunk]:
        ordered: list[str] = []
        if task.includes_metadata:
            # Front matter first: that is where authors, venue and year are printed.
            ordered += [
                c.chunk_id
                for c in self._chunks
                if c.section_type == "front_matter" or c.pdf_page_start == 0
            ]
        ordered += [
            c.chunk_id for c in self._chunks if c.indexed and c.section_type in task.section_types
        ]
        if task.includes_terminology:
            ordered += [
                c.chunk_id for c in self._chunks if c.indexed and _ABBREVIATION.search(c.text)
            ]
        for query in task.queries:
            ordered += self._retrieved(query)

        chosen: list[_Chunk] = []
        seen: set[str] = set()
        used = 0
        for chunk_id in ordered:
            chunk = self._by_id.get(chunk_id)
            if chunk is None or chunk_id in seen:
                continue
            if used + chunk.token_count > self._budget:
                continue
            seen.add(chunk_id)
            chosen.append(chunk)
            used += chunk.token_count
        # Present passages in reading order.
        return sorted(chosen, key=lambda c: c.chunk_index)


# ----- Assembly -------------------------------------------------------------------------


class ResultAssembler:
    """Turns grounded LLM items into claims and evidence records with stable IDs."""

    def __init__(self) -> None:
        self.claims: list[Claim] = []
        self.evidence: list[EvidenceRecord] = []
        self.warnings: list[str] = []
        self.dropped_inferred = 0
        self.dropped_empty = 0
        self.unlocated_claims = 0

    def _next_claim_id(self) -> str:
        return f"CLM_{len(self.claims) + 1:03d}"

    def _next_evidence_id(self) -> str:
        return f"EVD_{len(self.evidence) + 1:03d}"

    def add_claim(
        self,
        *,
        category: ClaimCategory,
        text: str,
        origin: Origin,
        field_path: str,
        evidence: list[tuple[str, QuoteMatch, dict[str, Any]]],
        extraction_status: ExtractionStatus = ExtractionStatus.EXTRACTED,
    ) -> tuple[str, list[str]]:
        claim_id = self._next_claim_id()
        evidence_ids: list[str] = []
        for source_text, match, location in evidence:
            evidence_id = self._next_evidence_id()
            self.evidence.append(
                EvidenceRecord(
                    evidence_id=evidence_id,
                    claim_id=claim_id,
                    source_text=source_text,
                    quote_match=match,
                    **location,
                )
            )
            evidence_ids.append(evidence_id)
        self.claims.append(
            Claim(
                claim_id=claim_id,
                category=category,
                claim_text=text,
                origin=origin,
                extraction_status=extraction_status,
                evidence_ids=evidence_ids,
                field_path=field_path,
            )
        )
        return claim_id, evidence_ids

    @staticmethod
    def _origin(item: Grounded, path: str) -> Origin:
        segments = set(re.split(r"[.\[\]]", path))
        if segments & _INFERRED_LISTS:
            return Origin.SYSTEM_INFERRED
        if getattr(item, "definition_origin", None) == "general_explanation":
            return Origin.SYSTEM_EXPLANATION
        if segments & _AUTHOR_LISTS or getattr(item, "is_author_conclusion", False):
            return Origin.AUTHOR_CLAIMED
        return Origin.DIRECTLY_EXTRACTED

    def ground(
        self,
        item: Grounded,
        path: str,
        category: ClaimCategory,
        linker: EvidenceLinker,
        *,
        in_list: bool = False,
    ) -> bool:
        """Attach claim/evidence IDs to ``item``. Returns False if the item must be dropped.

        A list element without content is dropped. A scalar text field without content is
        kept as an explicit ``not_found`` placeholder (spec §5.6).
        """
        if isinstance(item, TextField):
            if not item.value or not item.value.strip():
                if in_list:
                    self.dropped_empty += 1
                    return False
                item.value, item.status, item.support = None, ExtractionStatus.NOT_FOUND, []
                return True
            if item.status == ExtractionStatus.NOT_FOUND:
                item.status = ExtractionStatus.EXTRACTED
        statement = item.statement()
        if not item.has_content() or not statement or not statement.strip():
            # An item with nothing to state cannot be a claim, and keeping it would put
            # unevidenced content (e.g. a bare number) into the analysis.
            self.dropped_empty += 1
            return False
        resolved = [linker.resolve(ref.passage_id, ref.quote) for ref in item.support]
        located = [r for r in resolved if r.quote_match != QuoteMatch.NOT_FOUND]
        origin = self._origin(item, path)
        if origin == Origin.SYSTEM_INFERRED and not located:
            # Spec §4.2B: an inferred item without supporting evidence is not kept.
            self.dropped_inferred += 1
            return False
        if not located:
            self.unlocated_claims += 1
        if any(r.corrected_passage for r in located):
            self.warnings.append(f"{path}: a quote was found in a different passage than cited")
        claim_id, evidence_ids = self.add_claim(
            category=category,
            text=statement,
            origin=origin,
            field_path=path,
            extraction_status=getattr(item, "status", ExtractionStatus.EXTRACTED),
            evidence=[
                (
                    r.source_text,
                    r.quote_match,
                    {
                        "chunk_id": r.chunk_id,
                        "pdf_page_index": r.pdf_page_index,
                        "displayed_page_number": r.displayed_page_number,
                        "section_name": r.section_name,
                    },
                )
                for r in resolved
            ],
        )
        item.claim_ids, item.evidence_ids, item.support = [claim_id], evidence_ids, []
        return True

    def walk(
        self, node: BaseModel, path: str, category: ClaimCategory, linker: EvidenceLinker
    ) -> int:
        """Ground every item in ``node``'s tree; returns how many claims were created."""
        before = len(self.claims)
        self._visit(node, path, category, linker)
        return len(self.claims) - before

    def _visit(
        self,
        node: BaseModel,
        path: str,
        category: ClaimCategory,
        linker: EvidenceLinker,
        *,
        in_list: bool = False,
    ) -> bool:
        """Ground ``node`` and its descendants. False means ``node`` must be dropped."""
        if isinstance(node, Grounded) and not self.ground(
            node, path, category, linker, in_list=in_list
        ):
            return False
        for name in type(node).model_fields:
            if name == "support":
                continue
            value = getattr(node, name)
            child_category: ClaimCategory = "dataset" if name == "datasets" else category
            if isinstance(value, BaseModel):
                self._visit(value, f"{path}.{name}", child_category, linker)
            elif isinstance(value, list) and any(isinstance(v, BaseModel) for v in value):
                kept: list[BaseModel] = []
                for element in value:
                    # The index is the element's final position, after any drops.
                    if self._visit(
                        element,
                        f"{path}.{name}[{len(kept)}]",
                        child_category,
                        linker,
                        in_list=True,
                    ):
                        kept.append(element)
                setattr(node, name, kept)
        return True


def _normalise_category_status(category: CategoryBase, claims_created: int) -> None:
    category.task_status = "completed"
    if claims_created and category.status == ExtractionStatus.NOT_FOUND:
        category.status = ExtractionStatus.EXTRACTED
    if not claims_created and category.status in (
        ExtractionStatus.EXTRACTED,
        ExtractionStatus.PARTIALLY_EXTRACTED,
    ):
        category.status = ExtractionStatus.NOT_FOUND
        category.note = (category.note or "") + " No supported content was extracted."
        category.note = category.note.strip()


# ----- Agent ----------------------------------------------------------------------------


class ExtractionAgent:
    def __init__(
        self,
        llm: LLMService,
        session_factory: sessionmaker[Session],
        chroma_client: ClientAPI,
        embedder: Embedder,
        *,
        token_budget: int = 6000,
        candidates: int = 8,
    ) -> None:
        self.llm = llm
        self.session_factory = session_factory
        self.chroma_client = chroma_client
        self.embedder = embedder
        self.token_budget = token_budget
        self.candidates = candidates

    def _load(
        self, document_id: str
    ) -> tuple[Document, list[_Chunk], dict[int, str], dict[int, str | None]]:
        with self.session_factory() as session:
            document = session.get(Document, document_id)
            if document is None:
                raise LookupError(f"Document {document_id} no longer exists.")
            rows = session.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index)
            )
            chunks = [
                _Chunk(
                    r.chunk_id,
                    r.chunk_index,
                    r.text,
                    r.section_name,
                    r.section_type,
                    r.pdf_page_start,
                    r.pdf_page_end,
                    r.displayed_page_start,
                    r.token_count,
                    r.indexed,
                )
                for r in rows
            ]
            pages = session.scalars(
                select(DocumentPage).where(DocumentPage.document_id == document_id)
            )
            page_texts, displayed = {}, {}
            for page in pages:
                page_texts[page.pdf_page_index] = page.page_text
                displayed[page.pdf_page_index] = page.displayed_page_number
            session.expunge(document)
        return document, chunks, page_texts, displayed

    def extract(self, document_id: str, workflow_run_id: str | None = None) -> ExtractionResult:
        document, chunks, page_texts, displayed = self._load(document_id)
        selector = PassageSelector(
            chunks,
            document_id=document_id,
            chroma_client=self.chroma_client,
            embedder=self.embedder,
            token_budget=self.token_budget,
            candidates=self.candidates,
        )
        result = ExtractionResult(
            processing_metadata=ProcessingMetadata(
                document_id=document_id,
                workflow_run_id=workflow_run_id,
                model_id=self.llm.model_id,
                embedding_model_id=document.embedding_model_id,
                prompt_version=PROMPT_VERSION,
                index_version=document.index_version,
                processing_status="completed",
            )
        )
        assembler = ResultAssembler()
        deterministic = (
            DocumentMetadata.model_validate(document.metadata_json)
            if document.metadata_json
            else DocumentMetadata()
        )
        pending = self._apply_deterministic_metadata(result, deterministic, displayed, assembler)

        # Passage selection is sequential (it uses the embedding model); the LLM calls run
        # in parallel; assembly runs in task order so claim IDs stay deterministic.
        prepared = [self._prepare(task, selector, page_texts, displayed) for task in TASKS]
        with ThreadPoolExecutor(max_workers=len(TASKS), thread_name_prefix="llm") as pool:
            futures = [
                pool.submit(self._call, task, item[0]) if item is not None else None
                for task, item in zip(TASKS, prepared, strict=True)
            ]
            outputs = [future.result() if future is not None else None for future in futures]
        for task, item, output in zip(TASKS, prepared, outputs, strict=True):
            record = self._assemble(task, item, output, result, assembler)
            result.processing_metadata.tasks.append(record)

        # Ambiguous or partial deterministic values get their claim only now, if the LLM
        # did not replace them with a better-supported value; no claim is left orphaned.
        for name, (text, status, evidence) in pending.items():
            value: MetadataValue = getattr(result.paper_metadata, name)
            if value.source == "deterministic" and not value.claim_ids:
                claim_id, evidence_ids = assembler.add_claim(
                    category="paper_metadata",
                    text=text,
                    origin=Origin.DIRECTLY_EXTRACTED,
                    field_path=f"paper_metadata.{name}",
                    evidence=evidence,
                    extraction_status=status,
                )
                value.claim_ids, value.evidence_ids = [claim_id], evidence_ids

        records = result.processing_metadata.tasks
        failed = sum(r.task_status == "failed" for r in records)
        result.processing_metadata.processing_status = (
            "failed" if failed == len(records) else "partial" if failed else "completed"
        )
        result.claims, result.evidence_registry = assembler.claims, assembler.evidence
        warnings = result.processing_metadata.warnings
        warnings.extend(assembler.warnings)
        if assembler.dropped_inferred:
            warnings.append(
                f"{assembler.dropped_inferred} system-inferred item(s) dropped: "
                "no supporting quote was found in the paper."
            )
        if assembler.dropped_empty:
            warnings.append(
                f"{assembler.dropped_empty} empty item(s) returned by the model were dropped."
            )
        if assembler.unlocated_claims:
            warnings.append(
                f"{assembler.unlocated_claims} claim(s) have no quote located in "
                "the paper; they carry no page reference."
            )
        summary: dict[str, int] = {}
        for claim in result.claims:
            summary[claim.verification_status.value] = (
                summary.get(claim.verification_status.value, 0) + 1
            )
        result.processing_metadata.verification_summary = summary
        # Final structural validation of the complete output (spec FR-18).
        return ExtractionResult.model_validate(result.model_dump(mode="json"))

    def _prepare(self, task, selector, page_texts, displayed):
        """Select passages for a task; returns (passages, linker) or None if there are none."""
        chosen = selector.select(task)
        if not chosen:
            return None
        passages = [
            PromptPassage(f"P{i + 1:02d}", c.section_name, _page_label(c), c.text)
            for i, c in enumerate(chosen)
        ]
        linker = EvidenceLinker(
            [
                PassageSource(
                    p.passage_id,
                    c.chunk_id,
                    c.text,
                    c.section_name,
                    c.pdf_page_start,
                    c.pdf_page_end,
                )
                for p, c in zip(passages, chosen, strict=True)
            ],
            page_texts,
            displayed,
        )
        return passages, linker

    def _call(self, task: ExtractionTask, passages: list[PromptPassage]):
        """The task's LLM call; returns the structured result or the LLMError raised."""
        try:
            return self.llm.generate_structured(
                task.response_model,
                system_instruction=SYSTEM_INSTRUCTION,
                prompt=build_prompt(task.prompt, passages),
            )
        except LLMError as exc:
            return exc

    def _assemble(self, task, prepared, output, result, assembler) -> TaskRecord:
        """Turn one task's output into claims and evidence (runs in task order)."""
        name = task.prompt.name
        if prepared is None:
            self._mark(task, result, "not_run", "No relevant passages were found for this task.")
            return TaskRecord(task=name, task_status="not_run", passages=0)
        passages, linker = prepared
        if isinstance(output, LLMError):
            logger.warning("Extraction task %s failed: %s", name, output.code)
            self._mark(task, result, "failed", f"Extraction failed: {output.message}")
            return TaskRecord(
                task=name,
                task_status="failed",
                passages=len(passages),
                error=f"{output.code}: {output.message}",
            )

        response = output.value
        for field_name, (part, attribute) in task.targets.items():
            category: CategoryBase = getattr(response, field_name)
            created = assembler.walk(category, f"{part}.{attribute}", _CATEGORY[field_name], linker)
            container = getattr(result, part)
            if attribute == "abstract":
                # Keep the deterministic verbatim abstract; it counts as content.
                category.original_abstract = container.abstract.original_abstract
                created += len(category.original_abstract.claim_ids)
            _normalise_category_status(category, created)
            setattr(container, attribute, category)
        if isinstance(response, MetadataResponse):
            self._apply_llm_metadata(result.paper_metadata, response, assembler, linker)
        return TaskRecord(
            task=name,
            task_status="completed",
            attempts=output.attempts,
            passages=len(passages),
            input_tokens=output.usage.input_tokens,
            output_tokens=output.usage.output_tokens,
            duration_ms=output.duration_ms,
            model_version=output.model_version,
        )

    @staticmethod
    def _mark(task: ExtractionTask, result: ExtractionResult, task_status: str, note: str) -> None:
        for part, attribute in task.targets.values():
            category: CategoryBase = getattr(getattr(result, part), attribute)
            category.task_status = task_status  # type: ignore[assignment]
            category.note = note
        if task.includes_metadata:
            for name in ("authors", "journal_or_conference", "publication_year", "keywords"):
                value: MetadataValue = getattr(result.paper_metadata, name)
                if value.status != ExtractionStatus.EXTRACTED:
                    value.note = note

    # ----- Metadata -----------------------------------------------------------------

    @staticmethod
    def _apply_deterministic_metadata(
        result: ExtractionResult,
        metadata: DocumentMetadata,
        displayed: dict[int, str | None],
        assembler: ResultAssembler,
    ) -> dict[str, tuple[str, ExtractionStatus, list[tuple[str, QuoteMatch, dict[str, Any]]]]]:
        """Copy deterministic metadata into the result.

        Extracted values get their claim at once. Ambiguous or partial values are returned
        as pending (the LLM metadata task may replace them) and get their claim later.
        """
        pending: dict[
            str, tuple[str, ExtractionStatus, list[tuple[str, QuoteMatch, dict[str, Any]]]]
        ] = {}
        target: PaperMetadata = result.paper_metadata
        for name in type(target).model_fields:
            field = getattr(metadata, name)
            value = MetadataValue(value=field.value, status=field.status, note=field.note)
            if field.value is not None and field.status != ExtractionStatus.NOT_FOUND:
                value.source = "deterministic"
                from_pdf_metadata = field.source == "pdf_metadata"
                page = None if from_pdf_metadata else field.pdf_page_index
                location = {
                    "chunk_id": None,
                    "pdf_page_index": page,
                    "displayed_page_number": displayed.get(page) if page is not None else None,
                    "section_name": None,
                }
                evidence = []
                if field.evidence_text:
                    match = QuoteMatch.PDF_METADATA if from_pdf_metadata else QuoteMatch.EXACT
                    evidence = [(field.evidence_text, match, location)]
                text = field.value if isinstance(field.value, str) else str(field.value)
                if name == "abstract":
                    text = "The paper has an abstract."
                claim_text = f"{name.replace('_', ' ')}: {text}"
                if field.status != ExtractionStatus.EXTRACTED:
                    pending[name] = (claim_text, field.status, evidence)
                    setattr(target, name, value)
                    continue
                claim_id, evidence_ids = assembler.add_claim(
                    category="paper_metadata",
                    text=claim_text,
                    origin=Origin.DIRECTLY_EXTRACTED,
                    field_path=f"paper_metadata.{name}",
                    evidence=evidence,
                    extraction_status=field.status,
                )
                value.claim_ids, value.evidence_ids = [claim_id], evidence_ids
                if name == "abstract":
                    original = result.research_analysis.abstract.original_abstract
                    original.value, original.status = field.value, field.status
                    original.claim_ids, original.evidence_ids = [claim_id], evidence_ids
            setattr(target, name, value)
        return pending

    @staticmethod
    def _apply_llm_metadata(
        target: PaperMetadata,
        response: MetadataResponse,
        assembler: ResultAssembler,
        linker: EvidenceLinker,
    ) -> None:
        # Deterministic values take precedence; the LLM only fills fields still missing.
        fields: dict[str, tuple[Grounded, Any]] = {
            "authors": (response.authors, response.authors.names or None),
            "journal_or_conference": (
                response.journal_or_conference,
                response.journal_or_conference.value,
            ),
            "publication_year": (response.publication_year, response.publication_year.year),
            "keywords": (response.keywords, response.keywords.keywords or None),
        }
        for name, (item, value) in fields.items():
            current: MetadataValue = getattr(target, name)
            if current.status == ExtractionStatus.EXTRACTED or value is None:
                continue
            # Metadata must be visible in the paper: without a located quote it is not used
            # (and no claim is created for it).
            if not any(
                linker.resolve(ref.passage_id, ref.quote).quote_match != QuoteMatch.NOT_FOUND
                for ref in item.support
            ):
                current.note = "A value was proposed but no supporting quote was found; not used."
                continue
            assembler.ground(item, f"paper_metadata.{name}", "paper_metadata", linker)
            status = getattr(item, "status", ExtractionStatus.EXTRACTED)
            setattr(
                target,
                name,
                MetadataValue(
                    value=value,
                    status=ExtractionStatus.EXTRACTED
                    if status == ExtractionStatus.NOT_FOUND
                    else status,
                    source="llm",
                    claim_ids=item.claim_ids,
                    evidence_ids=item.evidence_ids,
                ),
            )
