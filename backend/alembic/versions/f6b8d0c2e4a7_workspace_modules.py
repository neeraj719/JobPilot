"""workspace modules: master.modules, user_module_settings, user_workspace_preferences

JobPilot becomes a suite of modules (Resume Studio, Job Apply, ...) behind a launcher.
Three new tables, nothing else changes, so the migration is purely additive:

``master.modules``
  the module catalog, seeded here: ``resume`` (enabled), ``apply`` (AVAILABLE but
  **switched off platform-wide** — the owner turns it on from Settings › Admin) and the
  ``insights`` placeholder (COMING_SOON, no ``home_path``). Columns: ``code`` (partial
  unique), name, tagline, description, lucide ``icon``, ``home_path`` (nullable),
  ``accent`` (a design-token name), ``sort_order``, ``is_enabled`` (the platform-wide
  switch), ``min_role`` (``USER`` / ``ADMIN``), ``status`` (``AVAILABLE`` / ``COMING_SOON``).
  The insert runs once, with the table; later changes are an admin's and are never
  overwritten (``workspace.service.ensure_catalog`` only adds missing codes).
``master.user_module_settings``
  one live row per (user, module) (partial unique): ``is_enabled`` (an admin can switch a
  module off for one user), ``is_pinned``, the user's ``sort_order``, ``last_opened_at``,
  ``open_count``.
``master.user_workspace_preferences``
  one live row per user (partial unique on ``user_id``): ``landing``
  (``LAUNCHER`` / ``LAST_MODULE``), ``last_module_id`` (FK, SET NULL), ``show_tips``.

All three carry the seven standard columns and the ``updated_at`` trigger. Runs unchanged
on SQLite (schema names resolve per dialect, partial predicates per dialect keyword).

Revision ID: f6b8d0c2e4a7
Revises: e5a7c9b1d3f6
Create Date: 2026-10-24
"""
from datetime import datetime, timezone
from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

from app.core.db_triggers import create_updated_at_triggers, drop_updated_at_triggers

# revision identifiers, used by Alembic.
revision: str = 'f6b8d0c2e4a7'
down_revision: Union[str, None] = 'e5a7c9b1d3f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MASTER = "master"
MODULES = "modules"
SETTINGS = "user_module_settings"
PREFERENCES = "user_workspace_preferences"
NOT_DELETED = "deleted_at IS NULL"
TS = sa.DateTime(timezone=True)

#: Frozen copy of ``app.models.workspace.DEFAULT_MODULES`` at the time of this migration
#: (a migration must not change meaning when the model module does).
#: ``(code, name, tagline, description, icon, home_path, accent, sort_order, is_enabled, status)``
CATALOG: tuple[tuple[str, str, str, str, str, str | None, str, int, bool, str], ...] = (
    (
        "resume",
        "Resume Studio",
        "Build, score and tailor your resume",
        "Create and edit resumes, check them against a job description (an estimate, not a "
        "promise) and keep a tailored version per role.",
        "FileText",
        "/resume",
        "primary",
        10,
        True,
        "AVAILABLE",
    ),
    (
        "apply",
        "Job Apply",
        "Discover jobs, apply with approval, track replies",
        "Matched jobs, the application queue you approve, applications, interviews, companies, "
        "the daily automation and the replies detected in Gmail.",
        "Briefcase",
        "/dashboard",
        "info",
        20,
        False,
        "AVAILABLE",
    ),
    (
        "insights",
        "Career Insights",
        "Market trends and salary signals - coming soon",
        "Hiring trends for your target roles and how your pipeline compares. Not available yet.",
        "LineChart",
        None,
        "warning",
        30,
        True,
        "COMING_SOON",
    ),
)


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _schema() -> str | None:
    """``master`` on PostgreSQL, ``None`` on SQLite, which has no schemas."""
    return None if _sqlite() else MASTER


def _fk(table: str) -> str:
    return f"{table}.id" if _sqlite() else f"{MASTER}.{table}.id"


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
    return [
        sa.ForeignKeyConstraint(["created_by"], [_fk("users")], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], [_fk("users")], ondelete="SET NULL"),
    ]


def _modules_table() -> sa.Table:
    return sa.table(
        MODULES,
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("tagline", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("icon", sa.String()),
        sa.column("home_path", sa.String()),
        sa.column("accent", sa.String()),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_enabled", sa.Boolean()),
        sa.column("min_role", sa.String()),
        sa.column("status", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", TS),
        sa.column("updated_at", TS),
        schema=_schema(),
    )


def upgrade() -> None:
    op.create_table(
        MODULES,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("tagline", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(length=40), nullable=False),
        sa.Column("home_path", sa.String(length=200), nullable=True),
        sa.Column("accent", sa.String(length=40), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("min_role", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        *_standard_columns(),
        *_audit_fks(),
        sa.PrimaryKeyConstraint("id"),
        schema=_schema(),
    )
    op.create_index("uq_modules_code_active", MODULES, ["code"], unique=True, schema=_schema(), **_where())

    op.create_table(
        SETTINGS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("is_pinned", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("last_opened_at", TS, nullable=True),
        sa.Column("open_count", sa.Integer(), nullable=False),
        *_standard_columns(),
        sa.ForeignKeyConstraint(["user_id"], [_fk("users")], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["module_id"], [_fk(MODULES)], ondelete="CASCADE"),
        *_audit_fks(),
        sa.PrimaryKeyConstraint("id"),
        schema=_schema(),
    )
    op.create_index("ix_user_module_settings_user_id", SETTINGS, ["user_id"], unique=False, schema=_schema())
    op.create_index("ix_user_module_settings_module_id", SETTINGS, ["module_id"], unique=False, schema=_schema())
    op.create_index(
        "uq_user_module_settings_user_module_active", SETTINGS, ["user_id", "module_id"],
        unique=True, schema=_schema(), **_where(),
    )

    op.create_table(
        PREFERENCES,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("landing", sa.String(length=20), nullable=False),
        sa.Column("last_module_id", sa.Uuid(), nullable=True),
        sa.Column("show_tips", sa.Boolean(), nullable=False),
        *_standard_columns(),
        sa.ForeignKeyConstraint(["user_id"], [_fk("users")], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["last_module_id"], [_fk(MODULES)], ondelete="SET NULL"),
        *_audit_fks(),
        sa.PrimaryKeyConstraint("id"),
        schema=_schema(),
    )
    op.create_index("ix_user_workspace_preferences_user_id", PREFERENCES, ["user_id"], unique=False, schema=_schema())
    op.create_index(
        "uq_user_workspace_preferences_user_active", PREFERENCES, ["user_id"], unique=True, schema=_schema(), **_where()
    )

    create_updated_at_triggers(op.get_bind(), [(MASTER, MODULES), (MASTER, SETTINGS), (MASTER, PREFERENCES)])

    now = datetime.now(timezone.utc)
    op.bulk_insert(
        _modules_table(),
        [
            {
                "id": uuid4(),
                "code": code,
                "name": name,
                "tagline": tagline,
                "description": description,
                "icon": icon,
                "home_path": home_path,
                "accent": accent,
                "sort_order": sort_order,
                "is_enabled": is_enabled,
                "min_role": "USER",
                "status": status,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
            for code, name, tagline, description, icon, home_path, accent, sort_order, is_enabled, status in CATALOG
        ],
    )


def downgrade() -> None:
    drop_updated_at_triggers(
        op.get_bind(), [(MASTER, MODULES), (MASTER, SETTINGS), (MASTER, PREFERENCES)], drop_function=False
    )
    op.drop_index("uq_user_workspace_preferences_user_active", table_name=PREFERENCES, schema=_schema())
    op.drop_index("ix_user_workspace_preferences_user_id", table_name=PREFERENCES, schema=_schema())
    op.drop_table(PREFERENCES, schema=_schema())
    op.drop_index("uq_user_module_settings_user_module_active", table_name=SETTINGS, schema=_schema())
    op.drop_index("ix_user_module_settings_module_id", table_name=SETTINGS, schema=_schema())
    op.drop_index("ix_user_module_settings_user_id", table_name=SETTINGS, schema=_schema())
    op.drop_table(SETTINGS, schema=_schema())
    op.drop_index("uq_modules_code_active", table_name=MODULES, schema=_schema())
    op.drop_table(MODULES, schema=_schema())
