from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.config import BACKEND_DIR
from app.database.connection import check_database, create_db_engine, create_session_factory


def _sqlite_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'test.db').as_posix()}"


def test_sqlite_connection_and_session(tmp_path: Path) -> None:
    engine = create_db_engine(_sqlite_url(tmp_path))
    check_database(engine)
    with create_session_factory(engine)() as session:
        assert session.execute(text("SELECT 1")).scalar_one() == 1
    assert (tmp_path / "test.db").exists()
    engine.dispose()


def test_foreign_keys_enforced(tmp_path: Path) -> None:
    engine = create_db_engine(_sqlite_url(tmp_path))
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
    engine.dispose()


def test_alembic_upgrade_runs_against_configured_url(tmp_path: Path) -> None:
    url = _sqlite_url(tmp_path)
    config = Config(str(BACKEND_DIR / "alembic.ini"), cmd_opts=Namespace(x=[f"db_url={url}"]))
    command.upgrade(config, "head")
    engine = create_db_engine(url)
    # No revisions exist yet in Phase 1; the database must still be reachable and untouched
    # by unexpected tables.
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    engine.dispose()
