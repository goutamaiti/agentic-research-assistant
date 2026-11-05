"""Pydantic request/response models for the HTTP API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# "configured" means settings are present but the service was not contacted.
ComponentState = Literal["ok", "error", "configured", "not_configured"]


class ComponentHealth(BaseModel):
    status: ComponentState
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    app_name: str
    version: str
    environment: str
    components: dict[str, ComponentHealth] = Field(
        description="Per-component state: database, vector_store, llm."
    )


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
