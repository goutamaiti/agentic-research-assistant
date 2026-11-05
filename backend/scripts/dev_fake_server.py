"""DEVELOPMENT ONLY: run the API with scripted test fakes, for UI work without an LLM.

Uses the fake embedder and the scripted fake LLM from ``tests/fakes.py`` and a separate
storage folder, and pre-loads one synthetic test paper. Its "analysis" is canned test
output, not a real analysis; never use it for results.

    .venv/Scripts/python scripts/dev_fake_server.py [storage_dir] [port]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.jobs import InlineJobRunner  # noqa: E402
from app.services.llm_service import LLMService  # noqa: E402
from tests.fakes import FakeEmbedder, FakeLLMTransport, FakeOcr, grounded_responder  # noqa: E402
from tests.pdf_factory import write_paper  # noqa: E402


def _responder(task, prompt, schema):
    if task == "assistant":
        import re

        ids = re.findall(r'<passage id="(P\d+)"', prompt)
        return {
            "answer": "(Test fixture answer) The hybrid retriever reached recall at five of 0.82.",
            "cited_passage_ids": ids[:1],
            "insufficient_evidence": not ids,
            "general_explanation": None,
        }
    return grounded_responder(task, prompt, schema)


def main() -> None:
    storage = Path(sys.argv[1] if len(sys.argv) > 1 else "../storage_dev_fake").resolve()
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8010
    settings = Settings(_env_file=None, storage_dir=storage, app_env="development")
    llm = LLMService(FakeLLMTransport(_responder), model_id="TEST-FIXTURE", sleep=lambda s: None)
    app = create_app(settings, embedder=FakeEmbedder(), ocr_engine=FakeOcr(available=False),
                     job_runner=InlineJobRunner(), llm_service=llm)
    with TestClient(app) as client:  # seed one synthetic paper
        if not client.get("/api/documents").json():
            pdf = write_paper(storage / "synthetic_test_paper.pdf", extra_paragraphs=4)
            doc = client.post("/api/documents/upload",
                              files={"file": (pdf.name, pdf.read_bytes())}).json()
            client.post(f"/api/documents/{doc['id']}/analyze")
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
