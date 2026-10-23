"""ats optimizer: job targets, job-description snapshots, ATS analyses, optimization suggestions

Four new tables in ``media`` (owned by the ats stream, ``notes/resume-studio-plan.md``):

``job_targets``
    A saved job opportunity (company + role + posting URL), its application status, the source
    and tailored resumes, and pointers to the latest JD snapshot / analysis. Unique per user by
    ``fingerprint`` through a **partial** unique index (``WHERE deleted_at IS NULL``), so a
    deleted target can be saved again (``docs/DATABASE.md`` rule 3).
``job_description_snapshots``
    Immutable copies of a job description with the extracted requirements.
``ats_analyses``
    Estimated ATS compatibility reports (resume version x snapshot), with polish status/progress.
``optimization_suggestions``
    The changes an analysis proposes and what the user did with them.

Every table carries the seven standard columns and its ``updated_at`` trigger. The target's two
back-pointers (``latest_snapshot_id``, ``last_analysis_id``) close a cycle with the tables that
reference the target, so those two foreign keys are added after the tables exist.

Purely additive; runs unchanged on SQLite (schema name and partial-index keyword resolved per
dialect, the late foreign keys added through ``batch_alter_table``).

Revision ID: b4d6f8a0c2e4
Revises: a9c3e5b7d1f0
Create Date: 2026-10-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.db_triggers import create_updated_at_triggers, drop_updated_at_triggers

# revision identifiers, used by Alembic.
revision: str = 'b4d6f8a0c2e4'
down_revision: Union[str, None] = 'a9c3e5b7d1f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "media"
TARGETS = "job_targets"
SNAPSHOTS = "job_description_snapshots"
ANALYSES = "ats_analyses"
SUGGESTIONS = "optimization_suggestions"
TABLES = (TARGETS, SNAPSHOTS, ANALYSES, SUGGESTIONS)
NOT_DELETED = "deleted_at IS NULL"
TS = sa.DateTime(timezone=True)


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _schema() -> str | None:
    """``media`` on PostgreSQL, ``None`` on SQLite, which has no schemas."""
    return None if _sqlite() else SCHEMA


def _ref(schema: str, table: str) -> str:
    """``schema.table.id`` on PostgreSQL, ``table.id`` on SQLite."""
    return f"{table}.id" if _sqlite() else f"{schema}.{table}.id"


def _where() -> dict[str, sa.sql.elements.TextClause]:
    key = "sqlite_where" if _sqlite() else "postgresql_where"
    return {key: sa.text(NOT_DELETED)}


def _standard_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("deleted_at", TS, nullable=True),
    ]


def _audit_fks() -> list[sa.ForeignKeyConstraint]:
    users = _ref("master", "users")
    return [
        sa.ForeignKeyConstraint(["created_by"], [users], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], [users], ondelete="SET NULL"),
    ]


def _index(table: str, column: str) -> None:
    op.create_index(f"ix_{table}_{column}", table, [column], unique=False, schema=_schema())


def upgrade() -> None:
    schema = _schema()
    users = _ref("master", "users")
    resumes = _ref("media", "resumes")

    op.create_table(
        TARGETS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_company", sa.String(length=255), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("role_title", sa.String(length=255), nullable=False),
        sa.Column("job_url", sa.String(length=2048), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("work_mode", sa.String(length=10), nullable=True),
        sa.Column("required_skills", sa.JSON(), nullable=False),
        sa.Column("deadline", TS, nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("follow_up_at", TS, nullable=True),
        sa.Column("source_resume_id", sa.Uuid(), nullable=True),
        sa.Column("tailored_resume_id", sa.Uuid(), nullable=True),
        sa.Column("tailored_resume_version", sa.Integer(), nullable=True),
        sa.Column("submitted_resume_version", sa.Integer(), nullable=True),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("latest_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("last_analysis_id", sa.Uuid(), nullable=True),
        sa.Column("last_analyzed_at", TS, nullable=True),
        *_standard_columns(),
        sa.ForeignKeyConstraint(["user_id"], [users], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], [_ref("master", "companies")], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_resume_id"], [resumes], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tailored_resume_id"], [resumes], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["application_id"], [_ref("transaction", "applications")], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], [_ref("unified", "jobs")], ondelete="SET NULL"),
        *_audit_fks(),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
    )
    _index(TARGETS, "user_id")
    _index(TARGETS, "normalized_company")
    _index(TARGETS, "status")
    op.create_index(
        "uq_job_targets_user_fingerprint_active", TARGETS, ["user_id", "fingerprint"],
        unique=True, schema=schema, **_where(),
    )

    op.create_table(
        SNAPSHOTS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_target_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("fetched_at", TS, nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("structured", sa.JSON(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("changed_from_previous", sa.Boolean(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        *_standard_columns(),
        sa.ForeignKeyConstraint(["user_id"], [users], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_target_id"], [_ref("media", TARGETS)], ondelete="CASCADE"),
        *_audit_fks(),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
    )
    _index(SNAPSHOTS, "user_id")
    _index(SNAPSHOTS, "job_target_id")

    op.create_table(
        ANALYSES,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("resume_id", sa.Uuid(), nullable=False),
        sa.Column("resume_version", sa.Integer(), nullable=False),
        sa.Column("job_target_id", sa.Uuid(), nullable=True),
        sa.Column("snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("previous_analysis_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("overall_score", sa.Integer(), nullable=True),
        sa.Column("category_scores", sa.JSON(), nullable=False),
        sa.Column("matched_keywords", sa.JSON(), nullable=False),
        sa.Column("missing_keywords", sa.JSON(), nullable=False),
        sa.Column("weak_items", sa.JSON(), nullable=False),
        sa.Column("parse_risks", sa.JSON(), nullable=False),
        sa.Column("methodology_version", sa.String(length=40), nullable=False),
        sa.Column("weights", sa.JSON(), nullable=False),
        sa.Column("ai_provider", sa.String(length=60), nullable=True),
        sa.Column("ai_model", sa.String(length=120), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("completed_at", TS, nullable=True),
        *_standard_columns(),
        sa.ForeignKeyConstraint(["user_id"], [users], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resume_id"], [resumes], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_target_id"], [_ref("media", TARGETS)], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["snapshot_id"], [_ref("media", SNAPSHOTS)], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["previous_analysis_id"], [_ref("media", ANALYSES)], ondelete="SET NULL"),
        *_audit_fks(),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
    )
    for column in ("user_id", "resume_id", "job_target_id", "snapshot_id", "status"):
        _index(ANALYSES, column)

    op.create_table(
        SUGGESTIONS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("target_path", sa.String(length=200), nullable=True),
        sa.Column("before", sa.Text(), nullable=True),
        sa.Column("after", sa.Text(), nullable=True),
        sa.Column("safe", sa.Boolean(), nullable=False),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
        sa.Column("confirmation_label", sa.String(length=300), nullable=True),
        sa.Column("estimated_gain", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("applied_version", sa.Integer(), nullable=True),
        sa.Column("checks", sa.JSON(), nullable=False),
        *_standard_columns(),
        sa.ForeignKeyConstraint(["analysis_id"], [_ref("media", ANALYSES)], ondelete="CASCADE"),
        *_audit_fks(),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
    )
    _index(SUGGESTIONS, "analysis_id")
    _index(SUGGESTIONS, "status")

    # The target's back-pointers, now that both referenced tables exist.
    with op.batch_alter_table(TARGETS, schema=schema) as batch:
        batch.create_foreign_key(
            "fk_job_targets_latest_snapshot_id", SNAPSHOTS, ["latest_snapshot_id"], ["id"],
            ondelete="SET NULL", referent_schema=schema,
        )
        batch.create_foreign_key(
            "fk_job_targets_last_analysis_id", ANALYSES, ["last_analysis_id"], ["id"],
            ondelete="SET NULL", referent_schema=schema,
        )

    create_updated_at_triggers(op.get_bind(), [(SCHEMA, table) for table in TABLES])


def downgrade() -> None:
    schema = _schema()
    # Only these tables' triggers: the shared function still serves every other table.
    drop_updated_at_triggers(op.get_bind(), [(SCHEMA, table) for table in TABLES], drop_function=False)
    with op.batch_alter_table(TARGETS, schema=schema) as batch:
        batch.drop_constraint("fk_job_targets_last_analysis_id", type_="foreignkey")
        batch.drop_constraint("fk_job_targets_latest_snapshot_id", type_="foreignkey")

    op.drop_index("ix_optimization_suggestions_status", table_name=SUGGESTIONS, schema=schema)
    op.drop_index("ix_optimization_suggestions_analysis_id", table_name=SUGGESTIONS, schema=schema)
    op.drop_table(SUGGESTIONS, schema=schema)

    for column in ("status", "snapshot_id", "job_target_id", "resume_id", "user_id"):
        op.drop_index(f"ix_{ANALYSES}_{column}", table_name=ANALYSES, schema=schema)
    op.drop_table(ANALYSES, schema=schema)

    op.drop_index(f"ix_{SNAPSHOTS}_job_target_id", table_name=SNAPSHOTS, schema=schema)
    op.drop_index(f"ix_{SNAPSHOTS}_user_id", table_name=SNAPSHOTS, schema=schema)
    op.drop_table(SNAPSHOTS, schema=schema)

    op.drop_index("uq_job_targets_user_fingerprint_active", table_name=TARGETS, schema=schema)
    for column in ("status", "normalized_company", "user_id"):
        op.drop_index(f"ix_{TARGETS}_{column}", table_name=TARGETS, schema=schema)
    op.drop_table(TARGETS, schema=schema)
