# Agentic RAG Framework for Automated Domain-Specific Knowledge Extraction

A single-paper research assistant. Each workspace processes **one** academic PDF, extracts
structured research knowledge with page/section evidence, records a verification status for
each claim against the source passages, and answers questions about that paper only.

- Requirements and scope: [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) (master specification)
- Progress, decisions, and test results: [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md)

**Status:** Phase 1 (project foundation) only. Nothing processes papers yet.

## Prerequisites

| Tool | Version used | Notes |
|------|--------------|-------|
| Python | 3.12.x | `requires-python >=3.12` |
| Node.js | 24.x (Vite 8 needs ^20.19 or >=22.12) | npm 11 |
| Tesseract OCR | not yet required | needed from Phase 2 for scanned pages |

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

## Tests and linting

```bash
cd backend && .venv/Scripts/python -m pytest && .venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .
cd frontend && npm test && npm run build
```

Routine tests never call the Gemini API.

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
```

Modules from the specification's folder structure are added in the phase that needs them.
