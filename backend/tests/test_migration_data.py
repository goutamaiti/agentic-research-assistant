"""Migrations must preserve existing data (regression: batch rebuild cascaded deletes)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from sqlalchemy import text

from app.database.connection import create_db_engine
from app.database.migrations import alembic_config


def test_upgrade_to_head_keeps_child_rows(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    config = alembic_config(url)
    command.upgrade(config, "9354e57a3371")
    engine = create_db_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO documents (id, original_filename, stored_filename, file_path, sha256, "
                "file_size, authors_json, status, created_at, updated_at) VALUES ('"
                + "a" * 32
                + "', 'p.pdf', 'a.pdf', 'uploads/a.pdf', '"
                + "b" * 64
                + "', 1, '[]', 'indexed', "
                "'2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO document_pages (document_id, pdf_page_index, page_text, ocr_used, "
                "extraction_status, char_count) VALUES ('"
                + "a" * 32
                + "', 0, 'x', 0, 'extracted', 1)"
            )
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_db_engine(url)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM document_pages")).scalar_one() == 1
        assert conn.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
    engine.dispose()
