# Agentic RAG Framework for Automated Domain-Specific Knowledge Extraction

A single-paper research assistant. Each workspace processes **one** academic PDF, extracts
structured research knowledge with page/section evidence, records a verification status for
each claim against the source passages, and answers questions about that paper only.

- Requirements and scope: [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) (master specification)
- Progress, decisions, and test results: [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md)

**Status:** Phases 1-2 implemented: upload, PDF processing (text, OCR fallback, pages,
sections, deterministic metadata) and indexing (ChromaDB + BM25). LLM extraction,
verification and the research assistant come in later phases.

## Prerequisites

| Tool | Version used | Notes |
|------|--------------|-------|
| Python | 3.12.x | `requires-python >=3.12` |
| Node.js | 24.x (Vite 8 needs ^20.19 or >=22.12) | npm 11 |
| Tesseract OCR | optional system install | needed only to read **scanned** pages; without it they are marked `ocr_unavailable` and the paper is `partially_indexed`. On Windows, e.g. the UB-Mannheim build; set `TESSERACT_CMD` if it is not on PATH |

## Setup

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # Windows
# .venv/bin/python -m pip install -r requirements-dev.txt     # macOS/Linux
cp .env.example .env    # then set GEMINI_API_KEY (needed only from Phase 3)
```

`requirements.txt` pins the direct dependencies. `requirements.lock.txt` is the full
`pip freeze` from the verified environment and can be used for an exact reproduction
(`pip install -r requirements.lock.txt`).

### Frontend

```bash
cd frontend
npm install
```

## Running

From `backend/` with the virtual environment active:

```bash
uvicorn app.main:create_app --factory --reload --port 8000
```

From `frontend/`:

```bash
npm run dev
```

Open http://localhost:5173. The page calls `/api/health` through the Vite dev proxy and
shows the status of the database, the vector store, and the LLM configuration.

If the backend runs on a different port, start Vite with `BACKEND_URL` set, for example
`BACKEND_URL=http://127.0.0.1:8010 npm run dev` (PowerShell:
`$env:BACKEND_URL="http://127.0.0.1:8010"; npm run dev`).

## Processing a paper (API)

```bash
curl -F "file=@paper.pdf;type=application/pdf" http://127.0.0.1:8000/api/documents/upload
curl -X POST http://127.0.0.1:8000/api/documents/<id>/analyze      # returns 202 at once
curl http://127.0.0.1:8000/api/documents/<id>/status               # poll: stages + metrics
curl http://127.0.0.1:8000/api/documents/<id>                      # pages, sections, metadata
```

The first analysis downloads the embedding model (~420 MB) from Hugging Face into the
standard cache. Interactive API docs: http://127.0.0.1:8000/docs.

## Tests and linting

```bash
cd backend && .venv/Scripts/python -m pytest && .venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .
cd frontend && npm test && npm run build
```

Routine tests use synthetic PDFs and fake embedding/OCR services: no network, no model
download, no Gemini calls. The real embedding model is exercised by opt-in integration
tests: `RUN_INTEGRATION=1 .venv/Scripts/python -m pytest -m integration`.

## Configuration

All backend settings come from environment variables or `backend/.env`. See
[backend/.env.example](backend/.env.example). Relative storage paths resolve against the
project root. Runtime data lives in `storage/`, which git ignores.

The Gemini API key is read **only by the backend**. The frontend has no environment
variables, and the browser talks only to same-origin `/api` routes.

## Layout

```text
backend/    FastAPI app (app/), Alembic migrations (alembic/), tests (tests/)
frontend/   React + Vite + Tailwind CSS v4
storage/    uploads/, chroma/, reports/, database/   (runtime data, not committed)
evaluation/ test_papers/ (public papers for manual checks, not committed)
```

Modules from the specification's folder structure are added in the phase that needs them.
