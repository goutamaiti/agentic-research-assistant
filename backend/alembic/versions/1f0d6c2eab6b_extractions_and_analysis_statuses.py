"""extractions table and analysis document statuses

Revision ID: 1f0d6c2eab6b
Revises: 9354e57a3371
Create Date: 2026-11-05 14:01:57.444317

Migrations are static snapshots: enum value lists are written out here rather than
imported from application code, so later code changes cannot alter past migrations.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1f0d6c2eab6b"
down_revision: str | Sequence[str] | None = "9354e57a3371"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_DOCUMENT_STATUSES = (
    "uploaded", "queued", "processing", "indexed", "partially_indexed", "failed",
)
_NEW_DOCUMENT_STATUSES = (
    "uploaded", "queued", "processing", "indexed", "partially_indexed", "analyzed",
    "partially_analyzed", "failed",
)


def _status_check(values: tuple[str, ...]) -> str:
    return "status IN ({})".format(", ".join(f"'{value}'" for value in values))


def upgrade() -> None:
    op.create_table(
        "extractions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.String(length=32), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=32), nullable=True),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("embedding_model_id", sa.String(length=255), nullable=True),
        sa.Column("index_version", sa.String(length=32), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("completed", "partial", "failed", name="extraction_status",
                    native_enum=False, create_constraint=True, length=32),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("extractions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_extractions_document_id"), ["document_id"],
                              unique=False)

    # SQLite cannot alter a CHECK constraint in place; batch mode recreates the table.
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_constraint("document_status", type_="check")
        batch_op.create_check_constraint("document_status",
                                         _status_check(_NEW_DOCUMENT_STATUSES))


def downgrade() -> None:
    op.execute(
        "UPDATE documents SET status = 'indexed' WHERE status = 'analyzed'"
    )
    op.execute(
        "UPDATE documents SET status = 'partially_indexed' WHERE status = 'partially_analyzed'"
    )
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_constraint("document_status", type_="check")
        batch_op.create_check_constraint("document_status",
                                         _status_check(_OLD_DOCUMENT_STATUSES))
    with op.batch_alter_table("extractions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_extractions_document_id"))
    op.drop_table("extractions")
