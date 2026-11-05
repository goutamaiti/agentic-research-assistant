"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session


def get_session(request: Request) -> Iterator[Session]:
    """One SQLAlchemy session per request, always closed."""
    with request.app.state.session_factory() as session:
        yield session
