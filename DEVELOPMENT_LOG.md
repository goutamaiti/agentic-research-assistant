# DEVELOPMENT_LOG.md

Running record of implementation work. Requirements live in
[PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) and are not changed here.

---

## Phase 1: Project foundation (2026-11-03)

**Status:** Complete. All Phase 1 acceptance criteria were checked (see below). Committed
as `6e6c2b1` on 2026-11-05.

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

---

## Phase 2: PDF processing and indexing (2026-11-05)

**Status:** Implemented and tested. Four of the five acceptance criteria are verified on a
real paper. The OCR criterion is verified with a test double only, because Tesseract is not
installed on the development machine (see "Acceptance criteria").

### Planned scope (stated before coding)

Upload, validation, SHA-256 duplicate detection, page-wise extraction, scanned-page
detection with OCR fallback, section identification, deterministic metadata,
section-aware chunking, embeddings, ChromaDB and BM25 indexing. No LLM calls, no LangGraph
(Phase 4), no RRF fusion (Phase 6), no deletion endpoint (Phase 7), no frontend pages
(Phase 8).

### Completed tasks

1. **Data model and migration:** SQLAlchemy models, plus the first Alembic migration
   `9354e57a3371`. It creates `documents`, `document_pages`, `document_sections`,
   `document_chunks` and `processing_runs`, with FK `ON DELETE CASCADE`, unique constraints
   (SHA-256, page index and chunk index per document), and CHECK constraints generated from
   the status enums. Timestamps are timezone-aware UTC (`UTCDateTime`). Migrations run
   automatically at startup.
2. **Upload** (`POST /api/documents/upload`):
   - the size limit is enforced while streaming (413);
   - the content is sniffed for `%PDF-` regardless of filename or content type (415);
   - encrypted (422 `encrypted_pdf`), corrupt or repaired-to-empty (422 `corrupt_pdf`) and
     empty files (400) are rejected;
   - a duplicate SHA-256 returns 409 `duplicate_document` with the existing `document_id`
     (offer reuse);
   - files get a safe internal name `<uuid>.pdf`; the stored path is relative to `storage/`;
   - no temp or orphan files are left on any failure path.
3. **Analysis run** (`POST /api/documents/{id}/analyze` returns 202 with `workflow_run_id`;
   `GET /status`):
   - four recorded stages: `upload_validation`, `document_extraction`,
     `section_identification`, `retrieval_indexing`;
   - each stage stores its timings and metrics; a failure marks later stages `skipped` and
     the document `failed`, with an actionable message;
   - unreadable pages give `partially_indexed`;
   - one background worker thread; claiming a document for a run is atomic, so two runs can
     never be queued at once;
   - on startup, unfinished runs are marked `interrupted`;
   - a failed run removes stale chunks and vectors, so a failed document never looks
     indexed.
4. **PDF parsing** (PyMuPDF):
   - text is extracted page by page with font size and boldness;
   - same-baseline fragments are merged (LaTeX "1" + "Introduction");
   - vertical or rotated text is excluded (arXiv margin stamps, figure labels) and counted
     in page warnings;
   - rotated pages use unrotated coordinates.
5. **Scanned pages / OCR:**
   - a page counts as scanned when it has images and fewer than `OCR_MIN_TEXT_CHARS`
     characters;
   - those pages are OCR'd with Tesseract (pytesseract), and the render size is capped at
     about 40 MP;
   - each page gets a status: `extracted`, `ocr_extracted`, `ocr_failed`,
     `ocr_unavailable` or `empty`.
6. **Page numbers:** `pdf_page_index` (zero-based) is always kept. The
   `displayed_page_number` comes from PDF page labels, or from header/footer numbers that
   agree with the offset most pages share. Otherwise it is `null` and never guessed.
7. **Boilerplate:** running headers/footers repeated on ≥40% of pages are detected, and
   page numbers are removed from body text.
8. **Sections:** detected from numbered headings that are styled as headings, known
   academic section names, and styled unnumbered headings that are not repeated text. The
   result is a hierarchy (levels and parents) with canonical types (`introduction`,
   `methodology`, `results`, …), plus an implicit `Front matter` section.
9. **Metadata (deterministic, explicit evidence only):**
   - title from the first-page layout, or plausible PDF metadata;
   - DOI only when labelled in front matter or margins;
   - year only from a front-matter ©/copyright/"published" statement;
   - abstract from its section, keywords from a "Keywords"/"Index Terms" line, and
     language from a heuristic;
   - authors only from PDF metadata (marked `ambiguous` if "Last, First" cannot be split
     safely);
   - every field has a status, a source, a page and the evidence text.
10. **Chunking:**
    - chunks never cross sections and paragraphs are kept whole;
    - an oversized paragraph is split at sentences, and only an oversized sentence by
      words;
    - overlap is whole sentences;
    - sizes are counted with the embedding model's own tokenizer: target 220 / overlap 40 /
      max 256 word pieces;
    - each chunk keeps its PDF page span, displayed page numbers and section;
    - References and Acknowledgements are stored but not embedded (`INDEX_REFERENCES`).
11. **Indexing:**
    - `multi-qa-mpnet-base-cos-v1` (normalised vectors), loaded lazily in the worker;
    - one cosine ChromaDB collection per document (`doc_<id>`) with the spec §10.9
      metadata;
    - the stored vector count is checked against the number of chunks before the document
      is reported indexed;
    - BM25 (`rank-bm25`) is built from the SQLite chunks, with technical tokens kept intact
      plus their component parts.
12. **Search (for verification only):** `retrieval_service.search_semantic` /
    `search_keyword` map hits back to SQLite rows with page and section, and refuse
    documents that are not indexed.
13. **Health:** added `embeddings` (configured, not loaded) and `ocr` (Tesseract found or
    not).

### Technical decisions (for review)

1. **Two added tables** beyond the spec's suggested ones:
   - `document_sections` gives the section hierarchy a persistent home;
   - `document_chunks` makes SQLite the source of truth for chunk text and page mapping,
     so BM25 needs no separate store and later citation checks have exact text.
   The spec calls its tables "suggested", so this does not change scope.
2. **PyMuPDF dict extraction rather than `pymupdf4llm`.** Font-level spans give explicit,
   testable control of page and section provenance.
3. **The analyze endpoint currently runs processing and indexing only.** It is the same
   endpoint the spec defines; Phase 4 wraps these stages as LangGraph nodes and adds
   extraction and verification.
4. **Chunk sizes are measured in model word pieces**, not words, as spec §6.2 says. The max
   is 256 rather than "≈250" because the model card says it was trained on inputs up to
   250 word pieces (truncation is at 512).
5. **The embedded text is "section title + chunk",** which gives section context, while the
   stored chunk text stays verbatim for citations. The prefix is dropped if it would
   exceed the model limit.
6. **Deterministic metadata is preliminary.** Fields such as authors and venue that
   parsing cannot establish reliably stay `not_found` with a note. The extraction phase
   (Phase 3) produces the final `paper_metadata`, with evidence.

### Tests and results

| Check | Result |
|-------|--------|
| Backend `pytest` (default) | **141 passed**, 2 skipped (opt-in integration) |
| Backend `pytest` with `RUN_INTEGRATION=1` (real embedding model) | **143 passed** |
| `ruff check` / `ruff format --check` | clean |
| Models vs. migrations (`compare_metadata`) | no differences |
| Live server (uvicorn, real background thread): upload → analyze → poll `/status` | 202 in 0.2 s; second analyze → 409; stages progressed; indexed after ~25 s |
| Server log contents | IDs, counts and durations only; no document text, no secrets |

Test files:
- `test_pdf_parser.py`: validation codes, page numbers, labels, boilerplate, OCR states,
  hyphenation.
- `test_structure_and_metadata.py`: section hierarchy and types; metadata statuses,
  sources and the no-guessing rules.
- `test_chunker_and_keyword.py`: section boundaries, token caps, sentence overlap, page
  spans, BM25, Chroma replace/delete/cosine.
- `test_documents_api.py`: upload errors, duplicates, safe filenames, analyze/status,
  partial and failed runs, workspace isolation, idempotent re-runs, recovery.
- `test_review_regressions.py`: one test per confirmed review finding, plus the real-paper
  layout cases.
- `test_integration_embeddings.py` (opt-in): real model dimensions and normalisation,
  tokenizer-based chunk caps, paraphrase retrieval.

The test files were written in parallel by four test-writing agents, which were allowed to
change tests only. They found 2 app bugs, both fixed: repaired-corrupt PDFs were reported as
"empty", and `COVID-`/`19` was joined as `COVID- 19`.

### Real-paper check: arXiv:1706.03762 ("Attention Is All You Need", public)

Stored in `evaluation/test_papers/` (git-ignored). 15 pages, 2.2 MB, all with a text layer.

- **First run exposed real layout problems:**
  - the vertical arXiv stamp was taken as the title and as a heading;
  - no numbered headings were found ("1" and "Introduction" are separate PDF lines);
  - figure labels became headings.
  These were fixed and covered by regression tests.
- **After the fixes:**
  - title "Attention Is All You Need" (first-page layout);
  - 25 sections with the correct hierarchy (e.g. 3.2.1 under 3.2 under 3);
  - displayed page numbers 2–15 on pages 1–14, and `null` on page 0, which has no printed
    number;
  - abstract extracted; DOI, year, keywords and authors `not_found` (none are labelled in
    the arXiv version, and nothing was guessed);
  - 61 chunks, 48 indexed (references and acknowledgements excluded), mean 165 and max 234
    word pieces, 0 over the model limit;
  - indexing took ~24 s on CPU, including model load.
- **Retrieval spot checks** (top-1 for both semantic and BM25):
  - the optimizer/learning-rate question returns section *Optimizer*, PDF page index 6,
    printed page 7;
  - the English-to-German BLEU question returns *Machine Translation*, printed page 8;
  - the self-attention-vs-recurrence question returns *Why Self-Attention*, printed page 6.
  These are manual spot checks, not an evaluation. Retrieval metrics on annotated papers
  belong to Phase 9.

### Independent review

A three-lens review (pipeline, provenance, security), followed by an adversarial verifier,
found 21 candidate issues. **12 were confirmed and fixed, each with a regression test:**
- *Metadata guessed from body text:* a cited year or a dataset DOI in the body was taken as
  the paper's own.
- *Authors split wrongly:* "Last, First" author metadata was broken into fake names.
- *Rotated pages:* body numbers were deleted as if they were page numbers.
- *Short pages:* text-only pages were reported as unreadable scans.
- *BM25 compounds:* searching `bert` did not match `bert-base`.
- *OCR on huge pages:* there was no render-size cap, so one page could fail the whole run.
- *Concurrent analyze:* two simultaneous requests could start two runs.
- *Failed re-runs:* old index counts stayed visible.
- *Timestamps:* API times had no UTC marker.
- *Hyphenation:* `state-of-the-art` lost its last hyphen at a line break.
- *Orphan uploads:* a failed DB commit could leave the uploaded file behind.
- *Token limit:* the embedding prefix could exceed the model limit; a guard and a metric
  were added.

**Not fixed (judged speculative or later-phase), recorded here:**
- the request body is spooled by Starlette before the size check (413 still returned);
- there is no page-count cap, which the spec does not define;
- there is no time limit on crafted decompression bombs;
- a heading merged into the middle of a block is missed;
- PDF page labels win over contradicting printed numbers.

### Commands run (main ones)

```bash
alembic revision --autogenerate -m "documents pages sections chunks runs"
python -m pytest -q ; RUN_INTEGRATION=1 python -m pytest -q
ruff check . ; ruff format --check .
curl -L -o evaluation/test_papers/arxiv_1706.03762.pdf https://arxiv.org/pdf/1706.03762
uvicorn app.main:create_app --factory --port 8010   # live check via .claude/launch.json
```

Downloads, approved by the user: the embedding model (~420 MB, Hugging Face cache) and the
arXiv paper (2.2 MB).

### Acceptance criteria

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Text-based academic PDF processes successfully | ✅ | arXiv:1706.03762 indexed (above); synthetic papers in tests |
| Page mappings are preserved | ✅ | PDF index and printed number kept separately on pages and chunks; null when not identifiable; tests for footers, labels, rotation, OCR pages |
| OCR is attempted on scanned pages | ✅ (real Tesseract, 2026-11-05) | Detection and the OCR path tested with `FakeOcr`; then verified with real Tesseract 5.4.0 (see "Update" below). Without Tesseract, pages are marked `ocr_unavailable` and the document is `partially_indexed`. |
| Chunks are searchable | ✅ | Semantic and BM25 search on the real paper and in tests; workspace isolation tested |
| Indexing errors are reported accurately | ✅ | Embedding and Chroma failures give `failed` with a code; later stages `skipped`; stale index removed; the document never claims to be indexed |

### Update 2026-11-05: real OCR verified

Tesseract was not installed during Phase 2 because it is a system program, not a pip
package: installing it changes the machine outside the project and needed the user's
approval. With that approval it was installed:

- `winget install --id UB-Mannheim.TesseractOCR` → Tesseract 5.4.0.20240606 at
  `C:\Program Files\Tesseract-OCR\` (installer hash verified by winget; English and OSD
  language data included). The installer does not add it to PATH, so
  `TESSERACT_CMD=C:/Program Files/Tesseract-OCR/tesseract.exe` is set in `backend/.env`
  (machine-specific, git-ignored).
- **Scanned page (image only, 150 dpi):** status `ocr_extracted`, mean word confidence
  95.7. All checked numbers and phrases were read exactly (`91.4`, `87.2`, `0.01`,
  "convolutional", "learning rate").
- **Full pipeline:** a text paper plus one scanned page is now `indexed` (previously
  `partially_indexed`); `document_extraction` reports `ocr_pages: [3]`, no unreadable
  pages. `/api/health` reports OCR `ok`.
- Limitation seen: OCR text is stored one line per block, so headings on scanned pages
  are only detected by name or numbering (no font information). Chunking is unaffected.
  OCR quality on real scanned papers (skew, noise, two columns) is still unmeasured.

### Known bugs and limitations

- **Real OCR is verified on a synthetic scan only** (see "Update" above); quality on real
  scanned papers is unmeasured.
- **Section detection is heuristic.** Subsection types are keyword-based: for example
  "Model Variations" under *Results* is typed `methodology`. Headings with unusual styling
  can be missed.
- **Two-column layouts** depend on PyMuPDF's block order. They are untested on real
  two-column papers so far; the test paper is single-column.
- **Tables, equations and figures** are kept only as plain text where a text layer exists.
  Vertical text in figures is dropped, and tables are not extracted as structured data.
- **Authors and venue** are not identified deterministically and are left to Phase 3. The
  language check only distinguishes "English" from "unclear".
- **The model loader contacts huggingface.co** for update checks even when the model is
  cached. Set `HF_HUB_OFFLINE=1` after the first download for fully offline use.
- **Indexing is CPU-only:** ~24 s for a 15-page paper, mostly embedding. This is a
  measurement on one machine, not a benchmark.
- **There is no delete endpoint yet** (Phase 7). Test data uploaded during the live check
  remains in `storage/`.
- Phase 2 is committed as `65a1317`.

### Next recommended task

**Phase 3: LLM integration and structured extraction.** Prerequisites:
- a Gemini API key in `backend/.env`;
- one real call to decide between `models.generate_content` + `response_json_schema` and
  the newer Interactions API (see the Phase 1 discussion items);
- review current Gemini data-use terms before using non-public papers.

Optionally, install Tesseract first and re-run a scanned-paper check to close the OCR
criterion with the real engine.

---

## Phase 3: LLM integration and structured extraction (2026-11-05)

**Status:** Implemented and tested against a scripted fake LLM. **Not yet verified against
the real Gemini API**, because no API key is configured. The user chose "build now, verify
later"; the real-API check is the remaining acceptance step (see "Acceptance criteria").

### Planned scope (stated before coding)

A reusable LLM service; Pydantic schemas for the full output contract (spec §5); versioned,
category-specific prompts; extraction of the 12 primary categories and 4 extra
capabilities; claim/evidence references; explicit missing and ambiguous states. Not in
scope: claim verification (Phase 5), LangGraph orchestration (Phase 4), RRF fusion
(Phase 6), relational claims/evidence tables (Phase 7).

### Completed tasks

1. **Schemas** (`schemas/evidence.py`, `schemas/extraction.py`):
   - claims (`CLM_###`) and evidence records (`EVD_###`) with stable IDs, the spec's status
     and origin enums, and `quote_match` (`exact`, `normalized`, `not_found`,
     `pdf_metadata`);
   - every category has a `status` and an app-owned `task_status`, so "absent from the
     paper" is never confused with "could not be processed";
   - author-stated and system-inferred content live in separate lists (limitations, future
     scope, contributions); term definitions carry `definition_origin`;
   - numerical results keep metric, value as printed, unit, condition, dataset and
     baseline, and their claim text includes the numbers;
   - `llm_json_schema()` gives the model an inlined schema with app-owned fields removed.
2. **LLM service** (`services/llm_service.py`):
   - `GeminiTransport` uses `models.generate_content` with `response_json_schema`; the key
     is passed explicitly, so a stray `GOOGLE_API_KEY` is never used;
   - bounded retries with exponential backoff for timeouts, 429 and 5xx, honouring
     `retryDelay`; bounded re-asks for invalid JSON; no retry for auth errors, bad
     requests or blocked responses;
   - output is parsed and validated with Pydantic in application code; app-owned fields the
     model returns are stripped;
   - token usage (including thinking tokens) and the served model version are recorded.
3. **Prompts** (`prompts/extraction.py`, `PROMPT_VERSION = "extraction-v1"`): a shared
   system instruction and 6 task prompts. Paper text is passed only inside `<passage>`
   tags as untrusted data; tag look-alikes in any letter case are neutralised and every
   attribute (section name, page label) is sanitised.
4. **Evidence linking** (`services/evidence_linker.py`): each quote the model cites is
   matched against the stored chunk text, exactly and then after normalising whitespace,
   quotes, dashes, ligatures and case. The exact source span is stored and located on its
   PDF page. A quote that cannot be found gets **no** page, section or chunk, so it can
   never become a citation. A wrong passage ID is corrected only when the quote is found
   in another supplied passage.
5. **Extraction agent** (`agents/extraction_agent.py`):
   - 6 fixed tasks per paper (overview, methods, experiments, outlook, terminology,
     metadata), each one LLM call; no open-ended loop;
   - passages: chunks from matching sections plus semantic and BM25 hits, deduplicated,
     within a token budget, in reading order;
   - a failed task marks only its own categories `failed`; the rest are still extracted;
   - system-inferred items without a located quote are dropped; empty items are dropped;
     unlocated claims are kept with a warning (Phase 5 classifies them);
   - deterministic metadata takes precedence; the LLM fills only missing fields, and only
     with a located quote;
   - the complete `ExtractionResult` is validated before it is stored.
6. **Pipeline and API:**
   - new non-fatal stage `knowledge_extraction`: without a key it is `skipped`; on failure
     the document stays indexed and searchable;
   - new statuses `analyzed` and `partially_analyzed`;
   - new `extractions` table (result JSON plus model, prompt, schema, embedding and index
     versions) and migration `1f0d6c2eab6b`;
   - `GET /api/documents/{id}/analysis` returns the latest validated analysis;
   - stale analyses are removed when the index is rebuilt, when a run fails, or when a
     processing stage was interrupted.
7. **Real-API check script:** `backend/scripts/verify_gemini.py` makes two small calls on
   invented text: one tiny schema, and the full `OverviewResponse` schema with an
   injection sentence.

### Technical decisions (for review)

1. **Structured output via `models.generate_content` + `response_json_schema`.** This is
   the method documented in the SDK reference. The current docs page also shows the newer
   Interactions API; both satisfy the spec. The call sits behind one adapter
   (`GeminiTransport`), so switching is local. To be confirmed with the real API.
2. **Six grouped tasks instead of one call per category or one huge call.** This keeps
   prompts focused (spec §7.4) and calls bounded (6 per paper).
3. **Claims are built by the application, not the model.** The model returns items with
   quotes; the application assigns IDs, resolves pages and decides origin from the field
   the item sits in. The model cannot set claim IDs, origins or page numbers.
4. **Categories are objects** (`{status, task_status, note, items...}`) rather than the
   bare lists of the spec's conceptual JSON (§5.3), so each category carries its own
   status.
5. **Unlocated claims are kept, not deleted.** They carry `quote_match: not_found`, no page
   reference and a warning; classifying them as unsupported is Phase 5's job.
6. **Term definitions default to `general_explanation`:** a definition counts as the
   paper's own only when the model says so explicitly (spec §4.2C).

### Tests and results

| Check | Result |
|-------|--------|
| Backend `pytest` (default) | **319 passed**, 2 skipped (opt-in integration) |
| `ruff check` / `ruff format --check` | clean |
| Migration upgrade, downgrade, re-upgrade on a test DB | OK |
| Migration with existing data (base → head) | child rows kept (regression test) |
| End-to-end with a scripted fake LLM | `analyzed`; 6 calls; 27 claims; traps handled |

New test files, written in parallel by four test-writing agents limited to tests (they
found no app bugs):
- `test_llm_service.py` (48): retries, backoff, invalid-output re-asks, error mapping, key
  never in errors.
- `test_evidence_and_schemas.py` (77): normalisation, span recovery, page location,
  schema strictness.
- `test_extraction_agent.py` (16): referential integrity, origins, traps, failure
  isolation, prompt safety, passage budget.
- `test_analysis_endpoint.py` (14): stage lifecycle, `/analysis`, re-runs, fatal failures,
  migration statuses.
- `test_phase3_review_regressions.py` (22) and `test_migration_data.py` (1): one test per
  confirmed review finding.

The scripted fake LLM (`tests/fakes.py`) deliberately includes a fabricated quote, an
unsupported inference, an injected claim ID, a wrong passage ID and an unsupported venue.
All are handled: the fabricated quote gets no page, the inference is dropped, the injected
ID is ignored, the passage is corrected, and the venue is not used.

### Independent review

A three-lens review (assembly, pipeline, spec and security) with an adversarial verifier
found 21 candidates. **12 were confirmed and fixed, each with a regression test:**
- *Critical: the migration deleted existing data.* SQLite rebuilt `documents` with
  foreign keys on, so the cascade wiped pages, sections, chunks and runs. Migrations now
  switch foreign keys off for the rebuild and run `foreign_key_check` afterwards. The
  development database had not been migrated, so nothing was lost.
- *Orphan claim* when the LLM replaced an ambiguous deterministic author value.
- *Empty items kept* with no evidence (e.g. a bare number), and empty list entries kept,
  including system-inferred ones.
- *Abstract category* read `not_found` although the verbatim abstract was present.
- *Claims always `extracted`*, even for ambiguous or partial items.
- *Blocked prompts retried* instead of reported as blocked.
- *Interrupted runs* left an old analysis visible, or failed a fully indexed paper.
- *Invalid API key* (HTTP 400) reported as "bad request".
- *Thinking tokens* missing from token counts.
- *Page label* not escaped in the prompt; *passage-tag guard* case-sensitive.

Also adopted from the verifier's "optional" list: numbers in numerical claim text, the
safer term-definition default, the served model version per task, and author conclusions
labelled `author_claimed`.

**Not fixed (judged later-phase or design), recorded here:** checking that an LLM
metadata value actually appears in its quote (Phase 5 entity checks); hidden PDF-metadata
authors taking precedence over visible ones.

### Acceptance criteria

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Output validates against Pydantic | ✅ (fake LLM) | Final `ExtractionResult.model_validate`; stored JSON re-validated by `/analysis` |
| Every category has a defined status | ✅ | `status` + `task_status` on every category; tests check defaults and failures |
| Missing data is not fabricated | ✅ (fake LLM) | Instructions + quote requirement; unlocated quotes get no page; unsupported inferences and metadata dropped |
| Numerical results retain context | ✅ | `ResultItem` fields; numbers in claim text |
| Claims reference evidence records | ✅ | Two-way referential-integrity tests |
| Model access and API method verified | ⏳ **pending** | Needs `GEMINI_API_KEY`; run `scripts/verify_gemini.py`, then one full analysis |

### Known bugs and limitations

- **No real LLM output has been seen yet.** Prompt quality, quote accuracy and schema
  acceptance by Gemini are unverified.
- The LLM JSON schema uses `anyOf`/`null` and `additionalProperties: false`; whether
  Gemini accepts every construct is part of the pending check.
- Grounding proves a quote exists in the paper, not that it supports the claim. That
  judgement is Phase 5.
- Passage selection is heuristic. A category whose content is outside the selected
  passages comes back `not_found`, which can mean "retrieval missed it".
- Each run costs 6 LLM calls plus any retries. Costs are not estimated here because
  pricing changes.
- Phase 3 is not committed yet.

**Open gaps from the fix re-check, accepted as limitations under Amendment A1** (none
creates a page citation for unsupported text or loses data on a normal run):
- Blank LLM metadata values (author names, keywords, venue) can show as `extracted`, and
  an LLM metadata claim's status can disagree with its field.
- If the overview task fails, the abstract category reads `not_found` although the
  verbatim abstract is present.
- The startup foreign-key check would block startup if a broken link already existed.
- A re-run that was only queued when the app stopped removes the previous results.
- A term without a definition is labelled `system_explanation`.
- Unicode look-alike tag text in a paper is not normalised before prompting (theoretical).

**Real Gemini check (2026-11-05):** the key authenticates and `gemini-3.8-flash` is listed,
but every call returned 503 "high demand". Still to be re-run.

### Next recommended task

Scope was reduced by **Amendment A1** in PROJECT_CONTEXT.md (lighter process, five remaining
steps). Next: re-run `scripts/verify_gemini.py`, then **Step 4: minimal LangGraph
orchestration**.

---

## Step 4: Minimal LangGraph orchestration (2026-11-05, Amendment A1)

**Done:** the analysis run is now a LangGraph `StateGraph`
(`backend/app/workflows/analysis_graph.py`, state in `graph_state.py`):
`upload_validation → document_extraction → section_identification → retrieval_indexing →
knowledge_extraction → finalize`. Each processing stage has a conditional edge that goes
to END on failure; knowledge extraction is non-fatal and always reaches `finalize`. The
state carries only IDs and status (spec §9); stage logic is unchanged and still records
progress in `processing_runs`. No loops: retries stay bounded in the LLM service. No
checkpointing (dropped by A1; interrupted runs are still handled by `recover()`).

**Tests:** 322 passed, 2 skipped. All existing pipeline tests now run through the graph;
`tests/test_analysis_graph.py` checks node order, routing to END on failure, and that no
document content is in the state.

**Gemini:** re-tried; still HTTP 503 "high demand" on `gemini-3.8-flash`.

**Next:** Step 5, verification.

---

## Speed-up and OpenRouter route (2026-11-05, Amendments A1/A2)

**Why it was slow (measured):** six LLM calls ran one after another (20–60 s each with
default thinking); Gemini returned 503 "high demand"; then the free-tier quota (20 requests
per day per model) ran out, and the retry logic waited up to 60 s per attempt although the
provider said "retry in ~19 h". A run took over 10 minutes.

**Changes:**
- **All LLM schema fields required.** Gemini omitted optional fields, so values and quotes
  were missing. On the real paper this took evidenced claims from 11/70 to 41/42 (all
  exact quotes). `PROMPT_VERSION` → `extraction-v3`.
- **3 merged calls, run in parallel** (overview+metadata, methods+terminology,
  experiments+outlook); selection and assembly stay sequential, so claim IDs are stable.
- **Low reasoning effort** (`LLM_THINKING_LEVEL=low`): the verification call used 862
  output tokens instead of 2,655.
- **Fail fast:** a retry hint over 60 s or HTTP 402 → `quota_exhausted`, no waiting; at
  most one retry for server errors. Measured: a run with no credit now ends in ~1 s
  instead of minutes.
- **OpenRouter transport** (Amendment A2): same model `google/gemini-3.8-flash`, strict
  JSON Schema, chosen automatically for an `sk-or-` key. Verified: model access, schema
  accepted, exact quote returned, prompt injection ignored.
- Output limit raised to 16,384 tokens (thinking counts toward it).

**Tests:** 330 passed, 2 skipped (8 new OpenRouter transport tests).

**Blocked:** the OpenRouter account has **$0 credit** (`total_credits: 0`; the $50 shown
is only the key's spending cap), so a full real analysis on the merged 3-call design has
not run yet. Re-run after credit is added.

---

## Step 5: Claim verification (2026-11-05, Amendment A1)

**Done:** `backend/app/agents/verification_agent.py`, run as the non-fatal graph stage
`evidence_verification` after extraction. Per claim:
- no evidence → `not_verifiable`; cited quote not found in the paper → `unsupported`;
  deterministic metadata whose value is in its exact quote → `verified` (no LLM call);
- other claims: one LLM judgement per batch of 20 (batches in parallel) → `verified` /
  `partially_supported` / `unsupported` / `contradicted`, with an explanation;
- a number in the claim that is not in its quotes caps the result at
  `partially_supported`;
- without an LLM, or if a batch fails, claims stay `pending` with the reason; nothing is
  verified by default.

The verified analysis replaces the stored `result_json`; `verification_summary` counts the
statuses. New endpoint `GET /api/documents/{id}/evidence` lists each claim with its
passages (spec §12.4).

**Tests:** 335 passed, 2 skipped (`tests/test_verification.py`: deterministic rules,
number downgrade, contradicted, pending without or with a failing LLM, the endpoint).
On the fake run: 23 verified, 2 partially supported (number gaps), 1 unsupported (the
planted fabricated quote), 1 not verifiable.

**Not done (A1):** targeted re-extraction for unsupported claims; recovery after an
interrupted verification reports the document as `indexed` although its analysis exists.
The real API is still untested for this step (Gemini returned 503).
