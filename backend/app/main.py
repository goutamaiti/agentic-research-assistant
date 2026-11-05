"""FastAPI application factory and entry point.

Run (from ``backend/``):  uvicorn app.main:create_app --factory --reload --port 8000

There is deliberately no module-level ``app`` object: building the app reads settings
and configures logging, which must not happen merely because a module was imported
(for example by the test suite).
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.agents.extraction_agent import ExtractionAgent
from app.agents.research_assistant import ResearchAssistant
from app.agents.verification_agent import VerificationAgent
from app.api import analysis, chat, documents, health, reports
from app.config import APP_NAME, APP_VERSION, Settings, get_settings
from app.database.connection import create_db_engine, create_session_factory
from app.database.migrations import upgrade_database
from app.document_processing.ocr import OcrEngine, TesseractOcr
from app.errors import AppError
from app.logging_config import configure_logging
from app.retrieval.embeddings import Embedder, SentenceTransformerEmbedder
from app.retrieval.vector_store import create_chroma_client
from app.schemas.api import ErrorDetail, ErrorResponse
from app.services.analysis_service import AnalysisService
from app.services.jobs import JobRunner, ThreadJobRunner
from app.services.llm_service import LLMService, build_transport

logger = logging.getLogger(__name__)


def _error(
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, details=details))
    return JSONResponse(
        status_code=status_code, content=body.model_dump(exclude_none=True), headers=headers
    )


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_request: Request, exc: AppError) -> JSONResponse:
        return _error(exc.status_code, exc.code, exc.message, details=exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Keep protocol headers such as Allow (405) that the default handler would send.
        return _error(exc.status_code, f"http_{exc.status_code}", str(exc.detail), exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Report field locations and messages only; never echo submitted values back.
        problems = "; ".join(
            f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        return _error(422, "validation_error", f"Invalid request: {problems}")

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _error(500, "internal_error", "An unexpected server error occurred.")


ACCESS_HEADER = "X-Access-Password"


def _register_access_check(app: FastAPI, settings: Settings) -> None:
    """Require the shared password on API calls when ACCESS_PASSWORD is set.

    Open: the health check (the UI uses it before anyone has typed the password) and
    report downloads, whose IDs are random 128-bit values only handed out to callers
    who already passed this check. The static frontend itself is public; it holds no data.
    """
    if settings.access_password is None:
        return
    expected = settings.access_password.get_secret_value().encode()

    @app.middleware("http")
    async def access_check(request: Request, call_next: Any) -> Any:
        path = request.url.path
        open_path = path == "/api/health" or (
            request.method == "GET" and path.startswith("/api/reports/")
        )
        if path.startswith("/api/") and not open_path and request.method != "OPTIONS":
            given = request.headers.get(ACCESS_HEADER, "").encode()
            if not hmac.compare_digest(given, expected):
                return _error(401, "access_denied", "This deployment needs its access password.")
        return await call_next(request)


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built React app (frontend/dist) at "/" when it exists.

    This gives a single process and a single address for the one-click launcher. API
    routes are registered first, so ``/api/...`` is never shadowed. During development
    the Vite dev server is used instead and this does nothing until a build exists.
    """
    from fastapi.staticfiles import StaticFiles

    from app.config import PROJECT_ROOT

    dist = PROJECT_ROOT / "frontend" / "dist"
    if (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")


def _default_llm_service(settings: Settings) -> LLMService | None:
    transport = build_transport(settings)
    if transport is None:
        return None
    return LLMService(
        transport,
        model_id=settings.llm_model_id,
        max_retries=settings.llm_max_retries,
        invalid_output_retries=settings.llm_invalid_output_retries,
        temperature=settings.llm_temperature,
        max_output_tokens=settings.llm_max_output_tokens,
    )


def create_app(
    settings: Settings | None = None,
    *,
    embedder: Embedder | None = None,
    ocr_engine: OcrEngine | None = None,
    job_runner: JobRunner | None = None,
    llm_service: LLMService | None = None,
) -> FastAPI:
    """Build the application.

    External services are injectable so tests can replace the embedding model, OCR
    engine, background runner and LLM; by default the real implementations are used.
    Without a Gemini API key there is no LLM service and knowledge extraction is skipped.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.ensure_storage_dirs()
        upgrade_database(settings.sqlalchemy_url)
        engine = create_db_engine(settings.sqlalchemy_url)
        runner = job_runner or ThreadJobRunner()
        try:
            session_factory = create_session_factory(engine)
            chroma_client = create_chroma_client(
                settings.chroma_path, anonymized_telemetry=settings.anonymized_telemetry
            )
            app.state.settings = settings
            app.state.db_engine = engine
            app.state.session_factory = session_factory
            app.state.chroma_client = chroma_client
            app.state.embedder = embedder or SentenceTransformerEmbedder(
                settings.embedding_model,
                device=settings.embedding_device,
                batch_size=settings.embedding_batch_size,
            )
            app.state.ocr_engine = ocr_engine or TesseractOcr(
                settings.tesseract_cmd, settings.ocr_language
            )
            llm = llm_service or _default_llm_service(settings)
            app.state.llm_service = llm
            extraction_agent = (
                ExtractionAgent(
                    llm,
                    session_factory,
                    chroma_client,
                    app.state.embedder,
                    token_budget=settings.extraction_passage_token_budget,
                    candidates=settings.semantic_candidates,
                )
                if llm is not None
                else None
            )
            app.state.analysis_service = AnalysisService(
                settings,
                session_factory,
                chroma_client,
                app.state.embedder,
                app.state.ocr_engine,
                runner,
                extraction_agent=extraction_agent,
                verification_agent=VerificationAgent(llm),
            )
            app.state.research_assistant = ResearchAssistant(llm, chroma_client, app.state.embedder)
            app.state.analysis_service.recover()
            # Mounted last, at startup, so it never shadows an API route.
            _mount_frontend(app)
            logger.info(
                "Started %s %s (env=%s, llm_configured=%s, model=%s)",
                APP_NAME,
                APP_VERSION,
                settings.app_env,
                settings.llm_configured,
                f"{settings.llm_model_id} via {settings.resolved_llm_provider}",
            )
            yield
        finally:
            runner.shutdown()
            engine.dispose()
            logger.info("Shutdown complete")

    app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", ACCESS_HEADER],
    )
    _register_error_handlers(app)
    _register_access_check(app, settings)
    app.include_router(health.router, prefix="/api")
    app.include_router(documents.router, prefix="/api")
    app.include_router(analysis.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(reports.router, prefix="/api")
    return app
