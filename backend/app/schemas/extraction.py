"""Structured research-analysis schema (specification §4, §5).

Design:
- *Item* models (``TextField``, ``ResultItem``, ...) are ``Grounded``: the LLM fills
  ``support`` with passage IDs and exact quotes; the application turns that support into
  claims and evidence records and fills ``claim_ids`` / ``evidence_ids``.
- *Category* models carry an explicit ``status`` (spec §5.2) and an app-owned
  ``task_status`` that says whether the extraction task ran at all, so "absent from the
  paper" is never confused with "could not be processed" (spec §14).
- Fields the application owns are removed from the JSON schema given to the LLM
  (``APP_OWNED_FIELDS``), so the model cannot fill them.
"""

from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.evidence import Claim, EvidenceRecord
from app.schemas.paper import ExtractionStatus

SCHEMA_VERSION = "1.0"

# Never shown to (or accepted from) the LLM.
APP_OWNED_FIELDS = frozenset({"claim_ids", "evidence_ids", "task_status", "original_abstract"})

TaskStatus = Literal["completed", "failed", "not_run"]


class _Model(BaseModel):
    # LLM output is validated strictly: unknown fields are an error, not silently kept.
    model_config = ConfigDict(extra="forbid")


class QuoteRef(_Model):
    passage_id: str = Field(description="ID of the passage the quote is copied from, e.g. 'P03'.")
    quote: str = Field(
        min_length=1,
        max_length=600,
        description="Exact words copied from that passage (no paraphrase, no ellipsis).",
    )


class Grounded(_Model):
    # Input from the LLM only: converted into evidence records, then left out of the result.
    support: list[QuoteRef] = Field(
        default_factory=list,
        exclude=True,
        description="Passages that state this item, each with an exact quote. Required for "
        "every item taken from the paper.",
    )
    claim_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)

    def statement(self) -> str | None:
        """The factual statement this item makes, used as the claim text."""
        raise NotImplementedError

    def has_content(self) -> bool:
        """False when the identifying fields are empty (the item says nothing)."""
        return True


def _filled(*values: str | None) -> bool:
    return all(value is not None and value.strip() for value in values)


class TextField(Grounded):
    value: str | None = Field(default=None, description="The extracted text, or null.")
    status: ExtractionStatus = ExtractionStatus.NOT_FOUND

    def statement(self) -> str | None:
        return self.value


class CategoryBase(_Model):
    status: ExtractionStatus = Field(
        default=ExtractionStatus.NOT_FOUND,
        description="extracted | partially_extracted | ambiguous | not_found (absent from the "
        "supplied passages).",
    )
    task_status: TaskStatus = "not_run"
    note: str | None = Field(default=None, description="Short note on gaps or ambiguity.")


# ----- Primary categories -------------------------------------------------------------


class AbstractAnalysis(CategoryBase):
    original_abstract: TextField = Field(default_factory=TextField)  # deterministic, verbatim
    stated_problem: TextField = Field(default_factory=TextField)
    approach: TextField = Field(default_factory=TextField)
    principal_findings: TextField = Field(default_factory=TextField)
    conclusion: TextField = Field(default_factory=TextField)


class ResearchProblem(CategoryBase):
    problem_statement: TextField = Field(default_factory=TextField)
    application_context: TextField = Field(default_factory=TextField)
    significance: TextField = Field(default_factory=TextField)
    specific_challenge: TextField = Field(default_factory=TextField)


class Objectives(CategoryBase):
    main_objective: TextField = Field(default_factory=TextField)
    specific_objectives: list[TextField] = Field(
        default_factory=list,
        description="Individual objectives. Not contributions and not results.",
    )


class Motivation(CategoryBase):
    reasons: list[TextField] = Field(
        default_factory=list, description="Why the authors did the research."
    )
    need: TextField = Field(
        default_factory=TextField, description="The practical or theoretical need."
    )
    shortcomings: list[TextField] = Field(
        default_factory=list, description="Shortcomings or unresolved issues motivating the work."
    )


class PriorApproach(Grounded):
    name: str = Field(description="Approach, method or line of work as named in the paper.")
    description: str = Field(description="What the paper says about it.")
    cited_as: str | None = Field(
        default=None, description="Citation marker as printed, e.g. '[12]'."
    )

    def statement(self) -> str | None:
        return f"{self.name}: {self.description}"

    def has_content(self) -> bool:
        return _filled(self.name, self.description)


class Background(CategoryBase):
    summary: TextField = Field(
        default_factory=TextField,
        description="Summary of the background the paper discusses (not an exhaustive review).",
    )
    prior_approaches: list[PriorApproach] = Field(default_factory=list)


class Methodology(CategoryBase):
    overall_approach: TextField = Field(default_factory=TextField)
    workflow: TextField = Field(default_factory=TextField)
    stages: list[TextField] = Field(default_factory=list, description="Major stages, in order.")
    implementation_procedure: TextField = Field(default_factory=TextField)
    experimental_methodology: TextField = Field(default_factory=TextField)


class ResultItem(Grounded):
    kind: Literal["numerical", "qualitative"]
    description: str = Field(description="The finding in the paper's terms, with its context.")
    metric: str | None = Field(default=None, description="Metric name, e.g. 'BLEU'.")
    value: float | None = Field(default=None, description="Numeric value if numerical.")
    value_text: str | None = Field(
        default=None, description="The value exactly as printed, e.g. '28.4'."
    )
    unit: str | None = None
    condition: str | None = Field(
        default=None, description="Experimental condition or model variant."
    )
    dataset_or_environment: str | None = None
    baseline: str | None = Field(default=None, description="What it is compared against.")
    is_author_conclusion: bool = Field(
        default=False, description="True if this is a conclusion drawn by the authors."
    )

    def statement(self) -> str | None:
        """The finding, prefixed by its numbers so they are part of the checked claim."""
        description = self.description.strip()
        if self.kind == "numerical" and _filled(self.metric, self.value_text):
            unit = f" {self.unit}" if self.unit else ""
            context = "; ".join(
                part
                for part in (
                    self.condition,
                    self.dataset_or_environment,
                    f"baseline: {self.baseline}" if self.baseline else None,
                )
                if part
            )
            numbers = f"{self.metric} = {self.value_text}{unit}" + (
                f" ({context})" if context else ""
            )
            return f"{numbers}: {description}" if description else numbers
        return description or None

    def has_content(self) -> bool:
        return _filled(self.description) or _filled(self.metric, self.value_text)


class Results(CategoryBase):
    items: list[ResultItem] = Field(default_factory=list)


class Limitations(CategoryBase):
    author_acknowledged: list[TextField] = Field(
        default_factory=list, description="Limitations the authors explicitly state."
    )
    system_inferred: list[TextField] = Field(
        default_factory=list,
        description="Possible limitations inferred cautiously from the paper; never presented "
        "as author statements. Each needs supporting passages.",
    )


class FutureScope(CategoryBase):
    author_proposed: list[TextField] = Field(
        default_factory=list, description="Future work explicitly proposed by the authors."
    )
    system_suggested: list[TextField] = Field(
        default_factory=list,
        description="Directions suggested by the system, clearly separate from the authors'.",
    )


# ----- Technical analysis -------------------------------------------------------------


class Parameter(Grounded):
    name: str
    value: str = Field(description="Value exactly as reported.")
    unit: str | None = None
    applies_to: str | None = Field(default=None, description="Model/experiment it applies to.")

    def statement(self) -> str | None:
        unit = f" {self.unit}" if self.unit else ""
        scope = f" ({self.applies_to})" if self.applies_to else ""
        return f"{self.name} = {self.value}{unit}{scope}"

    def has_content(self) -> bool:
        return _filled(self.name, self.value)


class AlgorithmModel(Grounded):
    name: str
    category: str | None = Field(default=None, description="Type, e.g. 'neural network'.")
    role: str | None = Field(default=None, description="Role in the research.")
    purpose: str | None = None
    implementation_details: str | None = None
    parameters: list[Parameter] = Field(default_factory=list)

    def statement(self) -> str | None:
        detail = self.role or self.purpose or self.category
        return f"The paper uses {self.name}" + (f" ({detail})" if detail else "") + "."

    def has_content(self) -> bool:
        return _filled(self.name)


class AlgorithmsAndModels(CategoryBase):
    items: list[AlgorithmModel] = Field(default_factory=list)


class Dataset(Grounded):
    name: str
    source: str | None = None
    size: str | None = Field(default=None, description="Size exactly as reported.")
    characteristics: str | None = None
    split: str | None = Field(default=None, description="Train/validation/test split.")

    def statement(self) -> str | None:
        parts = [f"Dataset: {self.name}"]
        parts += [
            f"{label} {value}"
            for label, value in (
                ("source", self.source),
                ("size", self.size),
                ("split", self.split),
            )
            if value
        ]
        return "; ".join(parts)

    def has_content(self) -> bool:
        return _filled(self.name)


class DatasetAndExperiments(CategoryBase):
    datasets: list[Dataset] = Field(default_factory=list)
    environment: TextField = Field(
        default_factory=TextField, description="Simulation or experimental environment."
    )
    hardware_software: TextField = Field(default_factory=TextField)
    experimental_parameters: list[Parameter] = Field(default_factory=list)
    evaluation_protocol: TextField = Field(default_factory=TextField)


class MethodologyStep(Grounded):
    step_number: int = Field(ge=1)
    operation: str
    input: str | None = None
    process: str | None = Field(default=None, description="Process or technique used.")
    output: str | None = None
    explanation: str | None = Field(
        default=None,
        description="Optional plain-language explanation that preserves the paper's meaning.",
    )

    def statement(self) -> str | None:
        return f"Step {self.step_number}: {self.operation}"

    def has_content(self) -> bool:
        return _filled(self.operation)


class MethodologyBreakdown(CategoryBase):
    steps: list[MethodologyStep] = Field(default_factory=list)


class ResearchContributions(CategoryBase):
    author_claimed: list[TextField] = Field(
        default_factory=list, description="Contributions the authors explicitly claim."
    )
    system_inferred: list[TextField] = Field(
        default_factory=list,
        description="Cautious interpretations, labelled as inferred; not novelty claims. Each "
        "needs supporting passages.",
    )


class Term(Grounded):
    term: str
    abbreviation: str | None = None
    definition: str | None = None
    # Defaults to the safe side: a definition counts as the paper's own only when the model
    # says so explicitly (spec §4.2C).
    definition_origin: Literal["paper_definition", "general_explanation"] = Field(
        default="general_explanation",
        description="'paper_definition' only when the paper itself defines the term; "
        "'general_explanation' when the paper uses the term without defining it.",
    )
    context: str | None = Field(default=None, description="How the term is used in the paper.")

    def statement(self) -> str | None:
        name = f"{self.term} ({self.abbreviation})" if self.abbreviation else self.term
        return f"{name}: {self.definition}" if self.definition else name

    def has_content(self) -> bool:
        return _filled(self.term)


class TechnicalTerminology(CategoryBase):
    terms: list[Term] = Field(default_factory=list)


# ----- Metadata -----------------------------------------------------------------------


MetadataValueSource = Literal["deterministic", "llm"]


class MetadataValue(_Model):
    value: Any = None
    status: ExtractionStatus = ExtractionStatus.NOT_FOUND
    source: MetadataValueSource | None = None
    claim_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    note: str | None = None


class PaperMetadata(_Model):
    title: MetadataValue = Field(default_factory=MetadataValue)
    authors: MetadataValue = Field(default_factory=MetadataValue)
    publication_year: MetadataValue = Field(default_factory=MetadataValue)
    journal_or_conference: MetadataValue = Field(default_factory=MetadataValue)
    doi: MetadataValue = Field(default_factory=MetadataValue)
    abstract: MetadataValue = Field(default_factory=MetadataValue)
    keywords: MetadataValue = Field(default_factory=MetadataValue)
    document_language: MetadataValue = Field(default_factory=MetadataValue)


class AuthorsField(Grounded):
    names: list[str] = Field(default_factory=list, description="Author names as printed.")
    status: ExtractionStatus = ExtractionStatus.NOT_FOUND

    def statement(self) -> str | None:
        return "Authors: " + ", ".join(self.names) if self.names else None


class KeywordsField(Grounded):
    keywords: list[str] = Field(default_factory=list)
    status: ExtractionStatus = ExtractionStatus.NOT_FOUND

    def statement(self) -> str | None:
        return "Keywords: " + ", ".join(self.keywords) if self.keywords else None


class YearField(Grounded):
    year: int | None = Field(default=None, ge=1900, le=2100)
    status: ExtractionStatus = ExtractionStatus.NOT_FOUND

    def statement(self) -> str | None:
        return f"Publication year: {self.year}" if self.year else None


# ----- LLM response models, one per extraction task -----------------------------------


class OverviewResponse(_Model):
    abstract: AbstractAnalysis
    research_problem: ResearchProblem
    objectives: Objectives
    motivation: Motivation
    background: Background


class MethodsResponse(_Model):
    methodology: Methodology
    algorithms_and_models: AlgorithmsAndModels
    methodology_breakdown: MethodologyBreakdown


class ExperimentsResponse(_Model):
    dataset_and_experiments: DatasetAndExperiments
    results: Results


class OutlookResponse(_Model):
    limitations: Limitations
    future_scope: FutureScope
    research_contributions: ResearchContributions


class TerminologyResponse(_Model):
    technical_terminology: TechnicalTerminology


class MetadataResponse(_Model):
    authors: AuthorsField
    journal_or_conference: TextField
    publication_year: YearField
    keywords: KeywordsField


# Merged task responses: three LLM calls per paper (Amendment A1 speed-up).


class OverviewTaskResponse(OverviewResponse, MetadataResponse):
    pass


class MethodsTaskResponse(MethodsResponse, TerminologyResponse):
    pass


class ExperimentsTaskResponse(ExperimentsResponse, OutlookResponse):
    pass


# ----- Final result (spec §5.3) -------------------------------------------------------


class ResearchAnalysis(_Model):
    abstract: AbstractAnalysis = Field(default_factory=AbstractAnalysis)
    research_problem: ResearchProblem = Field(default_factory=ResearchProblem)
    objectives: Objectives = Field(default_factory=Objectives)
    motivation: Motivation = Field(default_factory=Motivation)
    background: Background = Field(default_factory=Background)
    methodology: Methodology = Field(default_factory=Methodology)
    results: Results = Field(default_factory=Results)
    limitations: Limitations = Field(default_factory=Limitations)
    future_scope: FutureScope = Field(default_factory=FutureScope)


class TechnicalAnalysis(_Model):
    algorithms_and_models: AlgorithmsAndModels = Field(default_factory=AlgorithmsAndModels)
    dataset_and_experiments: DatasetAndExperiments = Field(default_factory=DatasetAndExperiments)
    methodology_breakdown: MethodologyBreakdown = Field(default_factory=MethodologyBreakdown)
    research_contributions: ResearchContributions = Field(default_factory=ResearchContributions)
    technical_terminology: TechnicalTerminology = Field(default_factory=TechnicalTerminology)


class TaskRecord(_Model):
    task: str
    task_status: TaskStatus
    attempts: int = 0
    passages: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None
    error: str | None = None
    model_version: str | None = None  # the model version the provider reports it served


class ProcessingMetadata(_Model):
    document_id: str
    workflow_run_id: str | None = None
    model_id: str
    embedding_model_id: str | None = None
    prompt_version: str
    schema_version: str = SCHEMA_VERSION
    index_version: str | None = None
    processing_status: Literal["completed", "partial", "failed"]
    verification_summary: dict[str, int] = Field(default_factory=dict)
    tasks: list[TaskRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExtractionResult(_Model):
    schema_version: str = SCHEMA_VERSION
    paper_metadata: PaperMetadata = Field(default_factory=PaperMetadata)
    research_analysis: ResearchAnalysis = Field(default_factory=ResearchAnalysis)
    technical_analysis: TechnicalAnalysis = Field(default_factory=TechnicalAnalysis)
    claims: list[Claim] = Field(default_factory=list)
    evidence_registry: list[EvidenceRecord] = Field(default_factory=list)
    processing_metadata: ProcessingMetadata


# ----- JSON schema for the LLM --------------------------------------------------------


def llm_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema for ``model`` as the LLM should see it.

    ``$ref``s are inlined (the schemas are not recursive), app-owned fields are removed,
    and ``title`` keys are dropped to keep the schema small.
    """
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].rsplit("/", 1)[-1]
                merged = {
                    **copy.deepcopy(definitions[name]),
                    **{k: v for k, v in node.items() if k != "$ref"},
                }
                return resolve(merged)
            out: dict[str, Any] = {}
            for key, value in node.items():
                if key == "title":
                    continue
                if key == "properties":
                    out[key] = {
                        name: resolve(prop)
                        for name, prop in value.items()
                        if name not in APP_OWNED_FIELDS
                    }
                elif key == "required":
                    continue  # recomputed below
                else:
                    out[key] = resolve(value)
            if "properties" in out:
                # Every field is required (nullable fields may still be null). Gemini omits
                # fields that are optional in the schema, which silently drops values and
                # supporting quotes (observed with gemini-3.6-flash on 2026-11-05).
                out["required"] = list(out["properties"])
            return out
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return resolve(schema)
