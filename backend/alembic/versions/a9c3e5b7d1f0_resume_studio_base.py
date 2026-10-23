"""resume studio base: resumes built in the editor, templates, tailoring links, AI-vs-user versions

Foundation for the resume builder / ATS optimizer work. Nothing new is required of
existing rows; every added column has a server default or is nullable.

``media.resumes``
  * ``kind``             UPLOADED (default, today's rows) | CREATED | TAILORED
  * ``template``         layout used by the preview and the PDF/DOCX export
  * ``source_resume_id`` the resume a TAILORED one was generated from (SET NULL on delete)
  * ``archived_at``      archive without deleting
  * ``draft_data`` / ``draft_saved_at``  editor autosave
  * the four file columns become nullable: a resume built in the editor has no original file

``media.resume_versions``
  * ``change_source``    USER | AI | SYSTEM, so AI edits stay distinguishable from the user's own
  * ``file_path`` nullable for the same reason

Runs unchanged on SQLite through ``batch_alter_table``.

Revision ID: a9c3e5b7d1f0
Revises: f3b8d1a6c920
Create Date: 2026-10-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a9c3e5b7d1f0'
down_revision: Union[str, None] = 'f3b8d1a6c920'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "media"
TS = sa.DateTime(timezone=True)


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _schema() -> str | None:
    """``media`` on PostgreSQL, ``None`` on SQLite, which has no schemas."""
    return None if _sqlite() else SCHEMA


def _resumes_ref() -> str:
    return "resumes.id" if _sqlite() else "media.resumes.id"


def upgrade() -> None:
    with op.batch_alter_table("resumes", schema=_schema()) as batch:
        batch.add_column(sa.Column("kind", sa.String(length=20), server_default="UPLOADED", nullable=False))
        batch.add_column(sa.Column("template", sa.String(length=40), server_default="classic", nullable=False))
        batch.add_column(sa.Column("source_resume_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("archived_at", TS, nullable=True))
        batch.add_column(sa.Column("draft_data", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("draft_saved_at", TS, nullable=True))
        batch.alter_column("file_path", existing_type=sa.String(length=1024), nullable=True)
        batch.alter_column("original_filename", existing_type=sa.String(length=255), nullable=True)
        batch.alter_column("mime_type", existing_type=sa.String(length=120), nullable=True)
        batch.alter_column("size_bytes", existing_type=sa.Integer(), nullable=True)
        batch.create_foreign_key(
            "fk_resumes_source_resume_id_resumes",
            "resumes",
            ["source_resume_id"],
            ["id"],
            ondelete="SET NULL",
            referent_schema=_schema(),
        )
    op.create_index("ix_resumes_source_resume_id", "resumes", ["source_resume_id"], unique=False, schema=_schema())

    with op.batch_alter_table("resume_versions", schema=_schema()) as batch:
        batch.add_column(sa.Column("change_source", sa.String(length=20), server_default="USER", nullable=False))
        batch.alter_column("file_path", existing_type=sa.String(length=1024), nullable=True)


def downgrade() -> None:
    schema = _schema()
    prefix = f"{schema}." if schema else ""
    # Rows without a file cannot satisfy NOT NULL again; give them an empty marker first.
    op.execute(sa.text(f"UPDATE {prefix}resume_versions SET file_path = '' WHERE file_path IS NULL"))
    op.execute(
        sa.text(
            f"UPDATE {prefix}resumes SET file_path = '', original_filename = '', mime_type = '', size_bytes = 0 "
            "WHERE file_path IS NULL OR original_filename IS NULL OR mime_type IS NULL OR size_bytes IS NULL"
        )
    )
    with op.batch_alter_table("resume_versions", schema=schema) as batch:
        batch.alter_column("file_path", existing_type=sa.String(length=1024), nullable=False)
        batch.drop_column("change_source")

    op.drop_index("ix_resumes_source_resume_id", table_name="resumes", schema=schema)
    with op.batch_alter_table("resumes", schema=schema) as batch:
        batch.drop_constraint("fk_resumes_source_resume_id_resumes", type_="foreignkey")
        batch.alter_column("size_bytes", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("mime_type", existing_type=sa.String(length=120), nullable=False)
        batch.alter_column("original_filename", existing_type=sa.String(length=255), nullable=False)
        batch.alter_column("file_path", existing_type=sa.String(length=1024), nullable=False)
        batch.drop_column("draft_saved_at")
        batch.drop_column("draft_data")
        batch.drop_column("archived_at")
        batch.drop_column("source_resume_id")
        batch.drop_column("template")
        batch.drop_column("kind")
