"""FastAPI application factory and entry point.

Run (from ``backend/``):  uvicorn app.main:create_app --factory --reload --port 8000

There is deliberately no module-level ``app`` object: building the app reads settings
and configures logging, which must not happen merely because a module was imported
(for example by the test suite).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import health
from app.config import APP_NAME, APP_VERSION, Settings, get_settings
from app.database.connection import create_db_engine, create_session_factory
from app.logging_config import configure_logging
from app.retrieval.vector_store import create_chroma_client
from app.schemas.api import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def _error(
    status_code: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message))
    return JSONResponse(status_code=status_code, content=body.model_dump(), headers=headers)


def _register_error_handlers(app: FastAPI) -> None:
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


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Pass ``settings`` to override configuration (e.g. in tests)."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.ensure_storage_dirs()
        engine = create_db_engine(settings.sqlalchemy_url)
        try:
            app.state.settings = settings
            app.state.db_engine = engine
            app.state.session_factory = create_session_factory(engine)
            app.state.chroma_client = create_chroma_client(
                settings.chroma_path, anonymized_telemetry=settings.anonymized_telemetry
            )
            logger.info(
                "Started %s %s (env=%s, llm_configured=%s, model=%s)",
                APP_NAME,
                APP_VERSION,
                settings.app_env,
                settings.llm_configured,
                settings.gemini_model,
            )
            yield
        finally:
            engine.dispose()
            logger.info("Shutdown complete")

    app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )
    _register_error_handlers(app)
    app.include_router(health.router, prefix="/api")
    return app
