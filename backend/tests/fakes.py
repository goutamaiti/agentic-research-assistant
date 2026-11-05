"""Test doubles for external services (embedding model, OCR, background runner)."""

from __future__ import annotations

import hashlib
import math
import re

from app.document_processing.ocr import OcrError, OcrLine, OcrResult

_WORD = re.compile(r"\w+|[^\w\s]")


class FakeEmbedder:
    """Deterministic hashed bag-of-words vectors: similar wording -> similar vectors.

    Token counting approximates a word-piece tokenizer by counting words and punctuation.
    """

    model_id = "test/fake-hash-embedder"
    dimensions = 256

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    @property
    def max_seq_length(self) -> int:
        return 512

    def count_tokens(self, text: str) -> int:
        return len(_WORD.findall(text))

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            digest = hashlib.md5(word.encode(), usedforsecurity=False).digest()
            vector[digest[0] % self.dimensions] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        from app.retrieval.embeddings import EmbeddingError

        self.calls += 1
        if self.fail:
            raise EmbeddingError("fake embedder failure")
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class FakeOcr:
    """Returns fixed text for every page, as if Tesseract had read it."""

    TEXT = [
        "Scanned page about convolutional networks.",
        "The scanned appendix describes image augmentation with random crops and flips.",
    ]

    def __init__(self, *, available: bool = True, fail: bool = False) -> None:
        self.available = available
        self.fail = fail
        self.calls = 0

    def is_available(self) -> bool:
        return self.available

    def recognize(self, png_bytes: bytes) -> OcrResult:
        assert png_bytes.startswith(b"\x89PNG")
        self.calls += 1
        if self.fail:
            raise OcrError("fake OCR failure")
        lines = [OcrLine(text=t, y0=100 + 40 * i, y1=120 + 40 * i) for i, t in enumerate(self.TEXT)]
        return OcrResult(lines=lines, mean_confidence=91.0)


# ----- LLM ------------------------------------------------------------------------------

_PASSAGE = re.compile(
    r'<passage id="(P\d+)" section="([^"]*)" page="[^"]*">\n(.*?)\n</passage>', re.DOTALL
)


def prompt_passages(prompt: str) -> list[tuple[str, str, str]]:
    """(passage_id, section, text) for each passage in an extraction prompt."""
    return _PASSAGE.findall(prompt)


def first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]


class FakeLLMTransport:
    """Scripted stand-in for the Gemini transport.

    Each physical call covers several sub-tasks (3 calls per paper). ``responder(subtask,
    prompt, schema)`` is called once per sub-task ("overview", "metadata", "methods",
    "terminology", "experiments", "outlook") and the answers are merged. It may raise an
    ``LLMError`` or return a string (raw, possibly invalid, output). Every physical call is
    recorded in ``calls`` with its primary task name and sub-tasks.
    """

    # Schema field that identifies a physical call -> (task name, sub-tasks).
    TASKS = {
        "abstract": ("overview", ("overview", "metadata")),
        "methodology": ("methods", ("methods", "terminology")),
        "results": ("experiments", ("experiments", "outlook")),
    }

    def __init__(self, responder) -> None:
        self.responder = responder
        self.calls: list[dict] = []
        self.verification_calls: list[dict] = []

    def generate(self, *, system_instruction, prompt, json_schema, temperature, max_output_tokens):
        import json

        from app.services.llm_service import LLMResponse, LLMUsage

        if "verdicts" in json_schema["properties"]:
            # Verification batches are recorded separately from extraction calls.
            self.verification_calls.append({"prompt": prompt, "system": system_instruction})
            answer = self.responder("verification", prompt, json_schema)
            text = answer if isinstance(answer, str) else json.dumps(answer)
            return LLMResponse(text=text, usage=LLMUsage(), model_version="fake-model-001")

        task, subtasks = next(
            spec for key, spec in self.TASKS.items() if key in json_schema["properties"]
        )
        self.calls.append(
            {
                "task": task,
                "subtasks": subtasks,
                "prompt": prompt,
                "system": system_instruction,
                "schema": json_schema,
            }
        )
        merged: dict = {}
        text = None
        for subtask in subtasks:
            answer = self.responder(subtask, prompt, json_schema)
            if isinstance(answer, str):
                text = answer
                break
            merged.update(answer)
        text = text if text is not None else json.dumps(merged)
        return LLMResponse(
            text=text,
            usage=LLMUsage(input_tokens=len(prompt) // 4, output_tokens=len(text) // 4),
            model_version="fake-model-001",
        )


def grounded_responder(task: str, prompt: str, schema: dict) -> dict:
    """A plausible answer quoting real passages, with deliberate traps:
    a fabricated quote, an unsupported inference, an injected app-owned field and a wrong
    passage ID."""
    if task == "verification":
        # Every claim is judged verified; the agent's deterministic rules still apply.
        claim_ids = re.findall(r"^CLAIM (CLM_\d+):", prompt, re.MULTILINE)
        return {
            "verdicts": [
                {"claim_id": cid, "status": "verified", "explanation": "The quote states it."}
                for cid in claim_ids
            ]
        }
    passages = prompt_passages(prompt)
    pid, _, text = passages[0]
    quote = first_sentence(text)
    support = [{"passage_id": pid, "quote": quote}]

    def field(value: str) -> dict:
        return {"value": value, "status": "extracted", "support": support}

    empty = {"value": None, "status": "not_found", "support": []}
    if task == "overview":
        return {
            "abstract": {
                "status": "extracted",
                "stated_problem": field(quote),
                "approach": empty,
                "principal_findings": empty,
                "conclusion": empty,
            },
            "research_problem": {
                "status": "extracted",
                "problem_statement": field(quote),
                "application_context": empty,
                "significance": empty,
                "specific_challenge": empty,
            },
            "objectives": {
                "status": "extracted",
                "main_objective": field(quote),
                "specific_objectives": [],
            },
            "motivation": {"status": "not_found", "reasons": [], "need": empty, "shortcomings": []},
            "background": {
                "status": "extracted",
                "summary": field(quote),
                "prior_approaches": [{"name": "BM25", "description": quote, "support": support}],
            },
        }
    if task == "methods":
        return {
            "methodology": {
                "status": "extracted",
                "overall_approach": field(quote),
                "workflow": empty,
                "stages": [field(quote)],
                "implementation_procedure": empty,
                "experimental_methodology": empty,
            },
            "algorithms_and_models": {
                "status": "extracted",
                "items": [
                    {
                        "name": "Reciprocal rank fusion",
                        "category": "rank fusion",
                        "role": "combines retrievers",
                        "parameters": [{"name": "k", "value": "60", "support": support}],
                        "support": support,
                    }
                ],
            },
            "methodology_breakdown": {
                "status": "extracted",
                "steps": [
                    {"step_number": 1, "operation": "Chunk the document", "support": support}
                ],
            },
        }
    if task == "experiments":
        return {
            "dataset_and_experiments": {
                "status": "partially_extracted",
                "datasets": [
                    {"name": "synthetic benchmark", "size": "forty questions", "support": support}
                ],
                "environment": empty,
                "hardware_software": empty,
                "experimental_parameters": [],
                "evaluation_protocol": field(quote),
            },
            "results": {
                "status": "extracted",
                "items": [
                    {
                        "kind": "numerical",
                        "description": quote,
                        "metric": "recall at five",
                        "value": 0.82,
                        "value_text": "0.82",
                        "baseline": "dense retrieval",
                        "support": support,
                    },
                    {  # fabricated quote: must not become a page citation
                        "kind": "qualitative",
                        "description": "The method is the best ever.",
                        "support": [{"passage_id": pid, "quote": "best ever published anywhere"}],
                    },
                ],
            },
        }
    if task == "outlook":
        return {
            "limitations": {
                "status": "extracted",
                "author_acknowledged": [field(quote)],
                # an inference without support: must be dropped
                "system_inferred": [
                    {"value": "Only one dataset was used.", "status": "extracted", "support": []}
                ],
            },
            "future_scope": {
                "status": "extracted",
                "author_proposed": [field(quote)],
                "system_suggested": [],
            },
            "research_contributions": {
                "status": "extracted",
                "author_claimed": [field(quote)],
                "system_inferred": [field(quote)],
            },
        }
    if task == "terminology":
        return {
            "technical_terminology": {
                "status": "extracted",
                "terms": [
                    {  # tries to fill an app-owned field: must be ignored
                        "term": "BM25",
                        "definition": "a ranking function",
                        "definition_origin": "paper_definition",
                        "support": support,
                        "claim_ids": ["CLM_999"],
                    },
                    {  # cites a wrong passage ID: the linker should still find the quote
                        "term": "Embedding",
                        "definition": "a vector representation",
                        "definition_origin": "general_explanation",
                        "support": [{"passage_id": "P99", "quote": quote}],
                    },
                ],
            }
        }
    return {  # metadata
        "authors": {
            "names": ["Ada Example", "Brian Placeholder"],
            "status": "extracted",
            "support": [{"passage_id": pid, "quote": "Ada Example and Brian Placeholder"}],
        },
        "journal_or_conference": {  # unsupported: must not be used
            "value": "Imaginary Conference",
            "status": "extracted",
            "support": [{"passage_id": pid, "quote": "Proceedings of Nowhere"}],
        },
        "publication_year": {"year": None, "status": "not_found", "support": []},
        "keywords": {"keywords": ["ignored"], "status": "extracted", "support": support},
    }
