from __future__ import annotations

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.database.connection import (
    Base,
    check_database,
    create_db_engine,
    create_session_factory,
)
from app.database.migrations import upgrade_database
from app.database.models import (
    Document,
    DocumentPage,
    DocumentStatus,
    PageExtractionStatus,
    ProcessingRun,
    RunStatus,
)

EXPECTED_TABLES = {
    "alembic_version",
    "documents",
    "document_pages",
    "document_sections",
    "document_chunks",
    "processing_runs",
}


def _sqlite_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'test.db').as_posix()}"


@pytest.fixture
def migrated_engine(tmp_path: Path):
    url = _sqlite_url(tmp_path)
    upgrade_database(url)
    engine = create_db_engine(url)
    yield engine
    engine.dispose()


def _document(doc_id: str = "a" * 32, sha: str = "b" * 64) -> Document:
    return Document(
        id=doc_id,
        original_filename="paper.pdf",
        stored_filename=f"{doc_id}.pdf",
        file_path=f"uploads/{doc_id}.pdf",
        sha256=sha,
        file_size=10,
    )


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


def test_migration_creates_expected_tables(migrated_engine) -> None:
    assert set(inspect(migrated_engine).get_table_names()) == EXPECTED_TABLES


def test_models_match_migrations(migrated_engine) -> None:
    """An empty autogenerate diff: the ORM models and the migration history agree."""
    with migrated_engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == []


def test_status_columns_reject_arbitrary_values(migrated_engine) -> None:
    factory = create_session_factory(migrated_engine)
    with factory() as session:
        session.add(_document())
        session.commit()
    with migrated_engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text("UPDATE documents SET status = 'almost_done'"))


def test_duplicate_sha256_rejected(migrated_engine) -> None:
    factory = create_session_factory(migrated_engine)
    with factory() as session:
        session.add(_document("a" * 32))
        session.commit()
        session.add(_document("c" * 32))
        with pytest.raises(IntegrityError):
            session.commit()


def test_deleting_document_cascades_to_children(migrated_engine) -> None:
    factory = create_session_factory(migrated_engine)
    with factory() as session:
        document = _document()
        document.status = DocumentStatus.INDEXED
        session.add(document)
        session.add(
            DocumentPage(
                document_id=document.id,
                pdf_page_index=0,
                page_text="x",
                extraction_status=PageExtractionStatus.EXTRACTED,
            )
        )
        session.add(
            ProcessingRun(
                document_id=document.id,
                workflow_run_id="r" * 32,
                stage="document_extraction",
                status=RunStatus.COMPLETED,
            )
        )
        session.commit()
    # Delete at the SQL level, so the database's ON DELETE CASCADE does the work.
    with migrated_engine.begin() as connection:
        connection.execute(text("DELETE FROM documents"))
    with factory() as session:
        assert session.scalars(select(DocumentPage)).all() == []
        assert session.scalars(select(ProcessingRun)).all() == []
