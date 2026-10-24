"""linkedin connections: master.linkedin_connections

"Connect LinkedIn" in Create Resume (official OAuth only: Sign In with LinkedIn using OpenID
Connect, plus the optional Member Data Portability API). One new table, purely additive:

``master.linkedin_connections``
  one live row per user (partial unique on ``user_id``): LinkedIn ``subject`` (``sub``),
  ``name``, ``email``, ``picture_url``, ``locale``, granted ``scopes`` (JSON),
  ``encrypted_access_token`` / ``encrypted_refresh_token`` (Fernet, never returned),
  ``token_expires_at``, ``status`` (``pending|connected|expired|revoked|error``),
  ``last_error``, ``connected_at``, ``last_synced_at``, ``auto_sync`` (default true),
  ``profile_snapshot`` (JSON: normalised identity + optional DMA / export data),
  ``snapshot_source`` (``oidc|dma|export``), ``export_imported_at``, ``last_sync_diff``
  (JSON), and the in-flight OAuth flow (``oauth_state`` = the signed state's ``jti``,
  ``encrypted_oauth_pending`` = encrypted PKCE verifier + OIDC nonce; both single use).

Seven standard columns and the ``updated_at`` trigger like every table. Runs unchanged on
SQLite (schema names resolve per dialect, partial predicates per dialect keyword).

This is a second head next to ``e6f8a0b2c4d7`` (ai-model-choice) on purpose: both branch
off ``f6b8d0c2e4a7``; integration merges the heads. Upgrade with
``alembic upgrade d2e4f6a8b0c1``, never ``head``.

Revision ID: d2e4f6a8b0c1
Revises: f6b8d0c2e4a7
Create Date: 2026-10-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.db_triggers import create_updated_at_triggers, drop_updated_at_triggers

# revision identifiers, used by Alembic.
revision: str = 'd2e4f6a8b0c1'
down_revision: Union[str, None] = 'f6b8d0c2e4a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MASTER = "master"
TABLE = "linkedin_connections"
NOT_DELETED = "deleted_at IS NULL"
TS = sa.DateTime(timezone=True)


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


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("picture_url", sa.String(length=1000), nullable=True),
        sa.Column("locale", sa.String(length=20), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", TS, nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("connected_at", TS, nullable=True),
        sa.Column("last_synced_at", TS, nullable=True),
        sa.Column("auto_sync", sa.Boolean(), nullable=False),
        sa.Column("profile_snapshot", sa.JSON(), nullable=False),
        sa.Column("snapshot_source", sa.String(length=10), nullable=True),
        sa.Column("export_imported_at", TS, nullable=True),
        sa.Column("last_sync_diff", sa.JSON(), nullable=False),
        sa.Column("oauth_state", sa.String(length=64), nullable=True),
        sa.Column("encrypted_oauth_pending", sa.Text(), nullable=True),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("deleted_at", TS, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], [_fk("users")], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], [_fk("users")], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], [_fk("users")], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema=_schema(),
    )
    op.create_index("ix_linkedin_connections_user_id", TABLE, ["user_id"], unique=False, schema=_schema())
    op.create_index(
        "uq_linkedin_connections_user_active", TABLE, ["user_id"], unique=True, schema=_schema(), **_where()
    )
    create_updated_at_triggers(op.get_bind(), [(MASTER, TABLE)])


def downgrade() -> None:
    drop_updated_at_triggers(op.get_bind(), [(MASTER, TABLE)], drop_function=False)
    op.drop_index("uq_linkedin_connections_user_active", table_name=TABLE, schema=_schema())
    op.drop_index("ix_linkedin_connections_user_id", table_name=TABLE, schema=_schema())
    op.drop_table(TABLE, schema=_schema())
