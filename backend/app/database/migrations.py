"""Programmatic Alembic upgrades (used at startup and in tests)."""

from __future__ import annotations

from argparse import Namespace

from alembic import command
from alembic.config import Config

from app.config import BACKEND_DIR


def alembic_config(database_url: str) -> Config:
    config = Config(
        str(BACKEND_DIR / "alembic.ini"), cmd_opts=Namespace(x=[f"db_url={database_url}"])
    )
    # Keep the application's logging configuration when migrating in-process.
    config.attributes["skip_logging_config"] = True
    return config


def upgrade_database(database_url: str) -> None:
    """Bring the database schema to the latest migration."""
    command.upgrade(alembic_config(database_url), "head")
