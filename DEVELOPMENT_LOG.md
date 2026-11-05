# DEVELOPMENT_LOG.md

Running record of implementation work. Requirements live in
[PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) and are not changed here.

---

## Phase 1: Project foundation (2026-11-03)

**Status:** Complete. All Phase 1 acceptance criteria were checked (see below). Nothing is
committed to git yet.

### Environment inspected

| Item | Found | Notes |
|------|-------|-------|
| OS | Windows 11 Home 10.0.26300 | |
| Python | 3.12.4 (3.11 also installed) | venv at `backend/.venv` |
| Node / npm | 24.19.0 / 11.17.0 | satisfies Vite 8 (`^20.19 \|\| >=22.12`) |
| Git | 2.51.0 | repository initialised, no remote, no commits |
| Tesseract | **not installed** | needed in Phase 2 for the OCR fallback |
| Ports | 8000 and 5173 in use by other local projects | see "Known issues" |

### Dependency compatibility check

Method: read current official docs, PyPI, npm and changelog pages (2026-11-03), then do
a trial install of the **whole** approved stack in one venv with exact pins. Results:

- `pip install` resolved; `pip check`: *No broken requirements found*.
- Smoke import of all key packages succeeded: `torch 2.15.0+cpu` (CUDA not available, as
  expected on this machine), `chromadb 1.5.9`, `onnxruntime 1.31.1`,
  `sentence-transformers 6.2.0`, `pymupdf 2.1`.
- `npm install`: 0 vulnerabilities. Peer ranges were checked:
  `@vitejs/plugin-react 6.2.1` needs Vite ^8, `@tailwindcss/vite 4.3.4` accepts Vite ^8,
  `vitest 5.1.0` accepts Vite ^8.

Pinned versions. Direct pins are in `backend/requirements.txt`, and the full freeze
(148 packages) is in `backend/requirements.lock.txt`:

| Python | Version | | Frontend | Version |
|--------|---------|-|----------|---------|
| fastapi | 0.162.0 | | react / react-dom | 19.3.1 |
| uvicorn[standard] | 0.54.0 | | vite | 8.3.5 |
| pydantic / pydantic-settings | 2.14.2 / 2.16.2 | | @vitejs/plugin-react | 6.2.1 |
| sqlalchemy / alembic | 2.1.6 / 1.20.1 | | tailwindcss / @tailwindcss/vite | 4.3.4 |
| chromadb | 1.5.9 | | vitest | 5.1.0 |
| google-genai | 2.34.0 | | | |
| langgraph / langchain-core | 1.2.19 / 1.7.4 | | | |
| sentence-transformers / torch | 6.2.0 / 2.15.0 | | | |
| pymupdf / pdfplumber / pytesseract | 2.1 / 0.11.10 / 0.3.13 | | | |
| rank-bm25 / reportlab / python-docx | 0.2.2 / 5.1.0 / 1.2.0 | | | |
| pytest / httpx / ruff (dev) | 9.2.0 / 0.28.1 / 0.17.3 | | | |

Facts confirmed from official sources that matter to later phases:

- **Gemini model.** `gemini-3.8-flash` exists in the Gemini API and has been GA since
  2026-09-02 (models page and changelog). Flash models have been deprecated and silently
  re-routed within about 2 months of release (for example, `gemini-3.7-flash` was re-routed
  to 3.8 on 2026-10-08). The ID is therefore a setting (`GEMINI_MODEL`), and the model ID
  will be recorded with every analysis, as the spec already requires.
- **google-genai.** It reads `GEMINI_API_KEY` or `GOOGLE_API_KEY`, and `GOOGLE_API_KEY`
  **wins** if both are set. `.env.example` warns about this. Phase 3 should pass the key
  explicitly from settings.
- **ChromaDB 1.5.9** lists open CVEs (CVE-2026-45829/-45830/-45831/-45833) that affect the
  Chroma **HTTP server**. We use only the embedded `PersistentClient`, never `chroma run` or
  an exposed port, and telemetry is off. Re-check advisory GHSA-f4j7-r4q5-qw2c before any
  deployment.
- **Tailwind v4.** Uses the `@tailwindcss/vite` plugin and `@import "tailwindcss";`, with no
  `tailwind.config.js` or PostCSS config.

### Completed tasks

1. Initialised the git repository and the Python 3.12 virtual environment.
2. Installed the approved stack with exact pins and verified compatibility (above).
3. Added centralized typed configuration (`pydantic-settings`, `SecretStr` for the API key,
   validation of values, and relative paths resolved against the project root).
4. Added logging configuration (one format; no secrets or document content logged).
5. Set up the FastAPI application factory with a lifespan that creates the storage
   directories and initialises SQLite and ChromaDB. It also sets up CORS and structured
   error responses (`{"error": {"code", "message"}}`).
6. Added the SQLite engine (foreign keys enforced per connection), session factory, and
   SQLAlchemy 2.x `DeclarativeBase`.
7. Initialised Alembic. `env.py` takes its URL from app settings and uses `render_as_batch`
   for SQLite. There are no migrations yet; tables arrive in the phases that need them.
8. Added the embedded persistent ChromaDB client with a heartbeat check.
9. Added `GET /api/health`, which reports database, vector store and LLM configuration.
10. Initialised React + Vite + Tailwind CSS. A Phase 1 page shows backend health with text
    labels and symbols (status is never shown by colour alone).
11. Configured the Vite dev proxy for `/api` so the browser only calls same-origin paths.
12. Added `.env.example`, `.gitignore`, `README.md`, and this log.

### Files created

```text
.gitignore, README.md, DEVELOPMENT_LOG.md, .claude/launch.json
backend/requirements.txt, requirements-dev.txt, requirements.lock.txt, pyproject.toml, .env.example
backend/alembic.ini, alembic/env.py, alembic/script.py.mako, alembic/README   (alembic/versions/ has only .gitkeep)
backend/app/__init__.py, config.py, logging_config.py, main.py
backend/app/api/__init__.py, health.py
backend/app/database/__init__.py, connection.py
backend/app/retrieval/__init__.py, vector_store.py
backend/app/schemas/__init__.py, api.py
backend/tests/__init__.py, conftest.py, test_config.py, test_health.py, test_database.py, test_vector_store.py
frontend/package.json, package-lock.json, vite.config.js, index.html
frontend/src/main.jsx, App.jsx, index.css, components/HealthStatus.jsx, services/api.js, services/api.test.js
storage/{uploads,chroma,reports,database}/.gitkeep
```

`PROJECT_CONTEXT.md` was not modified.

### Commands run (main ones)

```bash
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install <pinned stack>; pip check; pip freeze > requirements.lock.txt
backend/.venv/Scripts/alembic init alembic
npm install                        # in frontend/
python -m pytest                   # in backend/
ruff check . ; ruff format --check .
npm test ; npm run build           # in frontend/
alembic current                    # against the default settings URL
```

### Tests and results

| Check | Result |
|-------|--------|
| Backend `pytest` | **21 passed** |
| Backend `pytest` with a hostile environment (`LOG_LEVEL=loud`, `MAX_UPLOAD_MB=5`, `GEMINI_API_KEY=…`, bogus `DATABASE_URL`) | **21 passed** (tests are isolated from the shell and from `backend/.env`) |
| `ruff check` / `ruff format --check` | clean |
| Frontend `vitest` | **4 passed** |
| `vite build` | succeeded (CSS 11.8 kB, so Tailwind utilities are generated) |
| Built bundle scanned for `GEMINI`, `AIza`, `api_key` | no matches |
| End-to-end in a browser: Vite (5180) → proxy → FastAPI (8010) `/api/health` | 200; page shows Database OK, Vector store OK, LLM "Not configured", no console errors |
| End-to-end with backend stopped | page shows "Backend unavailable" (502) with a start hint, not an endless spinner |
| `alembic current` with default settings | runs; uses `storage/database/app.db` |

The backend tests cover settings defaults versus the spec (30 MB, 2 retries, model ID,
embedding model), env overrides, rejection of invalid values, path resolution (including
Windows drive letters in SQLite URLs), the secret never appearing in reprs or responses,
health OK and degraded, structured 404/405/422 errors (405 keeps `Allow`; 422 does not echo
submitted values), the CORS allow-list, import having no side effects, SQLite FK
enforcement, Alembic upgrade, and Chroma persistence round-trip and deletion.

### Phase 1 acceptance criteria

| Criterion | Evidence |
|-----------|----------|
| Backend starts | uvicorn started; startup log line; health 200 |
| Frontend starts | Vite dev server started; page rendered |
| Frontend can reach backend | browser `/api/health` via proxy → 200, components rendered |
| Database connection works | health `database: ok`; FK pragma test; Alembic test |
| Secrets not exposed in frontend | key only in backend `SecretStr`; frontend has no env vars; health returns only configured/not configured; bundle scan clean; test asserts the key never appears in the health response |

### Technical decisions (for review)

1. **Repository root is `L:\NLP_RB`**, not a nested `agentic-research-assistant/` folder.
   `PROJECT_CONTEXT.md` already sat here, and the spec places it at the repo root.
2. **Uvicorn factory mode** (`uvicorn app.main:create_app --factory`). There is no
   module-level `app`, so importing the module never reads `.env` or configures logging.
   The independent review found that this had been leaking developer config into tests.
3. **The health check never calls Gemini.** It reports `configured` / `not_configured`, so
   health polling cannot spend API quota. Overall `degraded` reflects only the local stores
   (database, vector store).
4. **ChromaDB is embedded only**, with telemetry off and `allow_reset=False` (because of the
   CVEs above). Embeddings will be supplied by our Sentence Transformers model
   (`embedding_function=None`), so Chroma's default ONNX embedder is never used.
5. **The frontend was written by hand** instead of with `create-vite`, which still prompts
   interactively in some cases and adds boilerplate. The result is the minimal equivalent.
6. **Additions to the spec's folder layout:** `app/logging_config.py`, `pyproject.toml` (ruff
   and pytest config), `requirements-dev.txt`, `requirements.lock.txt`, `alembic/`,
   `frontend/src/components/HealthStatus.jsx`, and `.claude/launch.json` (local dev
   launcher only). No spec module was renamed.
7. **Ruff** is the backend lint/format tool. No frontend linter is set up yet (see below).

### Items needing discussion before later phases (requirements unchanged)

- **Gemini structured output API (Phase 3).** The current official structured-output page
  shows the newer Interactions API (`client.interactions.create(..., response_format=…)`).
  The SDK reference still documents `models.generate_content` with
  `response_mime_type="application/json"` + `response_json_schema`. Both satisfy the spec
  (structured output, validated in application code). I will verify both with one real
  call at the start of Phase 3 and propose one before coding against it.
- **PyMuPDF licence.** PyMuPDF is AGPL-3.0 or commercial. This is fine for a college
  project, but it should be stated in the final documentation. PyMuPDF 2.1 also installs
  `pymupdf4llm` and `pymupdf-layout` as dependencies.
- **Tesseract** is a system binary, not a pip package. It must be installed on this machine
  (for example the UB-Mannheim Windows build) before Phase 2's OCR work. Its path should be
  configurable via an env var rather than hardcoded.

### Known bugs and limitations

- On this machine, ports 8000 and 5173 are used by other local projects. `.claude/launch.json`
  therefore runs the backend on 8010 and Vite on 5180 with `BACKEND_URL`. The documented
  defaults (8000 / 5173) are unchanged. `launch.json` uses the Windows venv path.
- No frontend linter or formatter yet (only Vitest and the build). One could be added in
  Phase 8, when the UI grows.
- The CORS allow-list defaults to the 5173 origins. That only matters if the browser calls
  the backend directly; the Vite proxy does not need CORS.
- Nothing is committed yet, and there is no GitHub remote.
- Several installed packages (google-genai, langgraph, sentence-transformers, PDF and report
  libraries) are not used yet. They were installed to verify compatibility now, as Phase 1
  requires.

### Next recommended task

**Phase 2: PDF processing and indexing.** Prerequisites: install Tesseract and choose a few
public, text-based test papers. Start with the `documents` / `document_pages` models plus the
first Alembic migration, then upload validation (content-type sniffing, 30 MB limit,
encrypted/corrupt rejection, SHA-256 duplicate detection).
