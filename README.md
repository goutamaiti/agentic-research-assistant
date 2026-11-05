# Agentic RAG Framework for Automated Domain-Specific Knowledge Extraction

A single-paper research assistant. Upload **one** academic PDF; the system extracts
structured research knowledge (12 categories + methodology breakdown, contributions,
terminology), links every claim to quoted passages with page numbers, checks each claim
against its sources, and answers questions about that paper with page citations.

- Specification: [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) (with Amendments A1 reduced scope,
  A2 OpenRouter route)
- Work log, decisions, test results and limitations: [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md)

## How it works

```text
PDF ─► validate ─► page text (+OCR) ─► sections & metadata ─► chunks ─► ChromaDB + BM25
                                                                         │
     LangGraph workflow (backend/app/workflows/analysis_graph.py)        ▼
     knowledge extraction (3 parallel Gemini calls, quotes required) ─► claims + evidence
     ─► evidence verification (deterministic checks + LLM judgement) ─► stored analysis
Q&A: question ─► hybrid retrieval (semantic + BM25, RRF) ─► cited answer or "insufficient evidence"
```

Evidence rules: a quote the model cites must be found in the stored text, or it gets no
page reference and the claim is `unsupported`. Unresolved claims are never marked
`verified`. System inferences and explanations are labelled separately from author
statements.

## Requirements

| Tool | Version used | Notes |
|------|--------------|-------|
| Python | 3.12 | backend |
| Node.js | 24 (Vite needs ≥ 20.19 or ≥ 22.12) | frontend |
| Tesseract OCR | 5.4 (optional) | only for scanned pages; Windows: `winget install --id UB-Mannheim.TesseractOCR` |
| LLM API key | Google Gemini *or* OpenRouter | without a key, papers are indexed but not analysed |

## Install

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt    # macOS/Linux: .venv/bin/python
cp .env.example .env
```

Edit `backend/.env`: set `GEMINI_API_KEY` (a Google AI Studio key, or an OpenRouter
`sk-or-…` key, which is detected automatically). If Tesseract is not on PATH, set
`TESSERACT_CMD`. The first analysis downloads the embedding model (~420 MB).

```bash
cd frontend
npm install
```

## Run

```bash
cd backend && .venv/Scripts/python -m uvicorn app.main:create_app --factory --port 8000
```

```bash
cd frontend && npm run dev
```

Open http://localhost:5173 (if the backend uses another port, start Vite with
`BACKEND_URL=http://127.0.0.1:<port>`).

## Demo

1. **Upload** a public paper (e.g. arXiv 1706.03762) on the home page; watch the stages
   (validation → extraction → sections → indexing → knowledge extraction → verification).
2. **Analysis**: metadata and all categories, each claim with origin, verification status
   and page; download the **PDF** or **JSON** report.
3. **Evidence**: filter claims by status; each shows its quoted passages and pages.
4. **Assistant**: ask e.g. "What optimizer was used?"; the answer cites pages; questions the
   paper does not answer get an explicit insufficient-evidence reply.

For UI work without an LLM, `backend/scripts/dev_fake_server.py` serves the app with
scripted **test** output (development only; never for results).

## API (all under `/api`)

`GET /health` · `POST /documents/upload` · `GET /documents` · `GET /documents/{id}` ·
`POST /documents/{id}/analyze` · `GET /documents/{id}/status` · `GET /documents/{id}/analysis` ·
`GET /documents/{id}/evidence` · `POST /documents/{id}/chat` · `GET /documents/{id}/chat/history` ·
`POST /documents/{id}/report` · `GET /reports/{report_id}`. Interactive docs: `/docs`.

## Tests and evaluation

```bash
cd backend && .venv/Scripts/python -m pytest
```

```bash
cd frontend && npm test
```

Routine tests use synthetic PDFs and fakes (no network, no paid calls). Evaluation
scripts (run from `backend/`):

```bash
.venv/Scripts/python ../evaluation/retrieval_tests.py ../evaluation/ground_truth/arxiv_1706.03762.json
```

```bash
.venv/Scripts/python ../evaluation/verification_tests.py ../evaluation/ground_truth/verification_claims_1706.03762.json
```

The label files in `evaluation/ground_truth/` are **drafts** and must be reviewed by a
person before any numbers are reported (see DEVELOPMENT_LOG.md for current results and
sample sizes).

## Limitations

Section detection and passage selection are heuristic; tables and figures are text only;
OCR quality on real scans is unmeasured; verification is automatic and can be wrong; the
system is an assistant for reading one paper, not an authority on scientific truth.
