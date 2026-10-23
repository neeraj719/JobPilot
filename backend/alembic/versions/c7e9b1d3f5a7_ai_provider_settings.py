"""ai provider settings: per-user provider/model routing, encrypted keys, usage events

Bring-your-own AI provider (AI Model Settings). Three new tables, nothing else changes, so
the migration is purely additive:

``master.ai_provider_settings``
  one live row per user (partial unique on ``user_id``): default provider/model, a
  per-workflow override map, the optional fallback (off by default), usage limits and the
  user's acknowledgement that hosted providers receive resume text.
``master.ai_provider_credentials``
  one live row per (user, provider) (partial unique): the Fernet-encrypted API key, a
  four-character hint, an optional base URL, ``credential_version`` (bumped on every save)
  and the last connection test. Removing a key tombstones the row and wipes the ciphertext,
  and the partial index lets the same provider be added again afterwards.
``transaction.ai_usage_events``
  append-only, one row per model call: tokens (``tokens_estimated`` when the SDK reported
  none), estimated cost, duration, outcome. Indexed on ``(user_id, created_at)``.

All three carry the seven standard columns and the ``updated_at`` trigger. Runs unchanged
on SQLite (schema names resolve per dialect, partial predicates per dialect keyword).

Revision ID: c7e9b1d3f5a7
Revises: a9c3e5b7d1f0
Create Date: 2026-10-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.db_triggers import create_updated_at_triggers, drop_updated_at_triggers

# revision identifiers, used by Alembic.
revision: str = 'c7e9b1d3f5a7'
down_revision: Union[str, None] = 'a9c3e5b7d1f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MASTER = "master"
TRANSACTION = "transaction"
SETTINGS = "ai_provider_settings"
CREDENTIALS = "ai_provider_credentials"
USAGE = "ai_usage_events"
NOT_DELETED = "deleted_at IS NULL"
TS = sa.DateTime(timezone=True)


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _schema(name: str) -> str | None:
    """The named schema on PostgreSQL, ``None`` on SQLite, which has no schemas."""
    return None if _sqlite() else name


def _users_fk() -> str:
    return "users.id" if _sqlite() else "master.users.id"


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


def _standard_fks() -> list[sa.ForeignKeyConstraint]:
    return [
        sa.ForeignKeyConstraint(["user_id"], [_users_fk()], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], [_users_fk()], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], [_users_fk()], ondelete="SET NULL"),
    ]


def upgrade() -> None:
    op.create_table(
        SETTINGS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("default_provider", sa.String(length=30), nullable=True),
        sa.Column("default_model", sa.String(length=200), nullable=True),
        sa.Column("workflow_models", sa.JSON(), nullable=False),
        sa.Column("fallback_provider", sa.String(length=30), nullable=True),
        sa.Column("fallback_model", sa.String(length=200), nullable=True),
        sa.Column("fallback_enabled", sa.Boolean(), nullable=False),
        sa.Column("daily_call_limit", sa.Integer(), nullable=True),
        sa.Column("monthly_budget_usd", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("data_residency_ack", sa.Boolean(), nullable=False),
        *_standard_columns(),
        *_standard_fks(),
        sa.PrimaryKeyConstraint("id"),
        schema=_schema(MASTER),
    )
    op.create_index("ix_ai_provider_settings_user_id", SETTINGS, ["user_id"], unique=False, schema=_schema(MASTER))
    op.create_index(
        "uq_ai_provider_settings_user_active", SETTINGS, ["user_id"], unique=True, schema=_schema(MASTER), **_where()
    )

    op.create_table(
        CREDENTIALS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column("key_hint", sa.String(length=8), nullable=True),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("credential_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_tested_at", TS, nullable=True),
        sa.Column("last_latency_ms", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_error_code", sa.String(length=40), nullable=True),
        sa.Column("rotated_at", TS, nullable=True),
        *_standard_columns(),
        *_standard_fks(),
        sa.PrimaryKeyConstraint("id"),
        schema=_schema(MASTER),
    )
    op.create_index("ix_ai_provider_credentials_user_id", CREDENTIALS, ["user_id"], unique=False, schema=_schema(MASTER))
    op.create_index(
        "uq_ai_provider_credentials_user_provider_active", CREDENTIALS, ["user_id", "provider"],
        unique=True, schema=_schema(MASTER), **_where(),
    )

    op.create_table(
        USAGE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("task", sa.String(length=80), nullable=False),
        sa.Column("workflow", sa.String(length=30), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("tokens_estimated", sa.Boolean(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.String(length=40), nullable=True),
        *_standard_columns(),
        *_standard_fks(),
        sa.PrimaryKeyConstraint("id"),
        schema=_schema(TRANSACTION),
    )
    op.create_index("ix_ai_usage_events_user_id", USAGE, ["user_id"], unique=False, schema=_schema(TRANSACTION))
    op.create_index(
        "ix_ai_usage_events_user_created_at", USAGE, ["user_id", "created_at"], unique=False, schema=_schema(TRANSACTION)
    )

    create_updated_at_triggers(op.get_bind(), [(MASTER, SETTINGS), (MASTER, CREDENTIALS), (TRANSACTION, USAGE)])


def downgrade() -> None:
    drop_updated_at_triggers(
        op.get_bind(), [(MASTER, SETTINGS), (MASTER, CREDENTIALS), (TRANSACTION, USAGE)], drop_function=False
    )
    op.drop_index("ix_ai_usage_events_user_created_at", table_name=USAGE, schema=_schema(TRANSACTION))
    op.drop_index("ix_ai_usage_events_user_id", table_name=USAGE, schema=_schema(TRANSACTION))
    op.drop_table(USAGE, schema=_schema(TRANSACTION))
    op.drop_index("uq_ai_provider_credentials_user_provider_active", table_name=CREDENTIALS, schema=_schema(MASTER))
    op.drop_index("ix_ai_provider_credentials_user_id", table_name=CREDENTIALS, schema=_schema(MASTER))
    op.drop_table(CREDENTIALS, schema=_schema(MASTER))
    op.drop_index("uq_ai_provider_settings_user_active", table_name=SETTINGS, schema=_schema(MASTER))
    op.drop_index("ix_ai_provider_settings_user_id", table_name=SETTINGS, schema=_schema(MASTER))
    op.drop_table(SETTINGS, schema=_schema(MASTER))
