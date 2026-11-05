"""Health-check endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.config import APP_NAME, APP_VERSION
from app.database.connection import check_database
from app.retrieval.vector_store import check_vector_store
from app.schemas.api import ComponentHealth, HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Report whether the backend and its local stores are usable.

    The LLM is reported as configured/not configured only; no paid API call is made.
    Overall status is ``degraded`` when the database or vector store is unavailable.
    """
    state = request.app.state
    components: dict[str, ComponentHealth] = {}

    try:
        check_database(state.db_engine)
        components["database"] = ComponentHealth(status="ok")
    except Exception as exc:  # report, never crash the health check
        logger.warning("Database health check failed: %s", type(exc).__name__)
        components["database"] = ComponentHealth(status="error", detail=type(exc).__name__)

    try:
        check_vector_store(state.chroma_client)
        components["vector_store"] = ComponentHealth(status="ok")
    except Exception as exc:
        logger.warning("Vector store health check failed: %s", type(exc).__name__)
        components["vector_store"] = ComponentHealth(status="error", detail=type(exc).__name__)

    settings = state.settings
    components["llm"] = ComponentHealth(
        status="configured" if settings.llm_configured else "not_configured",
        detail=f"model={settings.gemini_model}",
    )

    core_ok = all(components[name].status == "ok" for name in ("database", "vector_store"))
    return HealthResponse(
        status="ok" if core_ok else "degraded",
        app_name=APP_NAME,
        version=APP_VERSION,
        environment=settings.app_env,
        components=components,
    )
