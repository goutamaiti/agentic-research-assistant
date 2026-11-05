"""SQLite engine, session factory, and declarative base (SQLAlchemy 2.x)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import Pool


class Base(DeclarativeBase):
    """Declarative base for all ORM models (tables are added from Phase 2 onward)."""


def _enable_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    # SQLite does not enforce foreign keys unless asked to, per connection.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_db_engine(url: str, *, poolclass: type[Pool] | None = None) -> Engine:
    """Create an engine; for SQLite, allow use across FastAPI worker threads and enforce FKs."""
    is_sqlite = url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    kwargs: dict[str, Any] = {"connect_args": connect_args}
    if poolclass is not None:
        kwargs["poolclass"] = poolclass
    engine = create_engine(url, **kwargs)
    if is_sqlite:
        event.listen(engine, "connect", _enable_sqlite_pragmas)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)


def check_database(engine: Engine) -> None:
    """Raise if the database cannot be reached."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
