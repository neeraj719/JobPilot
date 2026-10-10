"""standing answers: master.standing_answers

Answers the user gives once and the answer engine reuses on every application
(consent, start date, notice period, relocation...). One new table, nothing else
changes, so the migration is purely additive.

The table carries the seven standard columns like every other one (``docs/DATABASE.md``
rule 6), its ``updated_at`` trigger, and a **partial** unique index on
``(user_id, question_key) WHERE deleted_at IS NULL`` (rule 3): deleting a standing answer
tombstones it, and saving the same question again must be able to re-use the key.

Runs unchanged on SQLite: the schema name is resolved per dialect and the partial index
predicate goes through the matching dialect keyword.

Revision ID: f3b8d1a6c920
Revises: e4c2a9f71b36
Create Date: 2026-10-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.db_triggers import create_updated_at_triggers, drop_updated_at_triggers

# revision identifiers, used by Alembic.
revision: str = 'f3b8d1a6c920'
down_revision: Union[str, None] = 'e4c2a9f71b36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "master"
TABLE = "standing_answers"
NOT_DELETED = "deleted_at IS NULL"
TS = sa.DateTime(timezone=True)


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _schema() -> str | None:
    """``master`` on PostgreSQL, ``None`` on SQLite, which has no schemas."""
    return None if _sqlite() else SCHEMA


def _users_fk() -> str:
    return "users.id" if _sqlite() else "master.users.id"


def _where() -> dict[str, sa.sql.elements.TextClause]:
    """Dialect keywords making an index partial on "not deleted", for this backend."""
    key = "sqlite_where" if _sqlite() else "postgresql_where"
    return {key: sa.text(NOT_DELETED)}


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("question_key", sa.String(length=120), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("field_type", sa.String(length=20), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("applies_to", sa.JSON(), nullable=False),
        sa.Column("expires_at", TS, nullable=True),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("deleted_at", TS, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], [_users_fk()], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], [_users_fk()], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], [_users_fk()], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema=_schema(),
    )
    op.create_index("ix_standing_answers_user_id", TABLE, ["user_id"], unique=False, schema=_schema())
    op.create_index(
        "uq_standing_answers_user_key_active", TABLE, ["user_id", "question_key"],
        unique=True, schema=_schema(), **_where(),
    )
    create_updated_at_triggers(op.get_bind(), [(SCHEMA, TABLE)])


def downgrade() -> None:
    # Only this table's trigger: the shared function still serves the other 27 tables.
    drop_updated_at_triggers(op.get_bind(), [(SCHEMA, TABLE)], drop_function=False)
    op.drop_index("uq_standing_answers_user_key_active", table_name=TABLE, schema=_schema())
    op.drop_index("ix_standing_answers_user_id", table_name=TABLE, schema=_schema())
    op.drop_table(TABLE, schema=_schema())
