"""Alembic environment. The database URL comes from app.config, never from alembic.ini."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

from app.config import get_settings
from app.database import models  # noqa: F401  (registers tables on Base.metadata)
from app.database.connection import Base, create_db_engine

config = context.config

if config.config_file_name is not None and not config.attributes.get("skip_logging_config"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    """Use `alembic -x db_url=...` when given (tests), else the application settings."""
    override = context.get_x_argument(as_dictionary=True).get("db_url")
    if override:
        return override
    settings = get_settings()
    settings.ensure_storage_dirs()
    return settings.sqlalchemy_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_db_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        is_sqlite = connection.dialect.name == "sqlite"
        if is_sqlite:
            # Batch mode rebuilds tables (copy, DROP, rename). With foreign keys enforced,
            # the DROP would fire ON DELETE CASCADE and wipe child rows. The pragma must be
            # set outside a transaction, so it is issued before migrations begin.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
        # render_as_batch lets Alembic emulate ALTER TABLE on SQLite.
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()
        if is_sqlite:
            violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
            if violations:
                raise RuntimeError(f"Migration left {len(violations)} foreign-key violation(s)")
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
