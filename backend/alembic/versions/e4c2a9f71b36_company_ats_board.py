"""public job board per company: companies.ats_board_token / ats_board_url

Adds the two columns the real discovery adapters (Greenhouse, Lever, Ashby,
SmartRecruiters) read: the company's board token on its ATS and the public board URL
the token was derived from. Both nullable, no default, so the ``ADD COLUMN`` is a
catalogue-only change on PostgreSQL and every existing company simply has no board.

It also normalises the existing ``ats_type`` values to the ``JobSourceType`` member
names (``greenhouse`` / ``Smart Recruiters`` -> ``GREENHOUSE`` / ``SMARTRECRUITERS``),
which is what the board lookup compares against. That rewrite is not reversible and
does not need to be: the downgrade leaves the canonical spelling in place.

Runs unchanged on SQLite: the schema name is resolved per dialect and the drop goes
through ``batch_alter_table``, which is a plain ``ALTER TABLE`` on PostgreSQL.

Revision ID: e4c2a9f71b36
Revises: b9f41c7d2e58
Create Date: 2026-10-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e4c2a9f71b36'
down_revision: Union[str, None] = 'b9f41c7d2e58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "companies"


def _schema() -> str | None:
    """``master`` on PostgreSQL, ``None`` on SQLite, which has no schemas."""
    return None if op.get_bind().dialect.name == "sqlite" else "master"


def _qualified() -> str:
    schema = _schema()
    return f'"{schema}"."{TABLE}"' if schema else f'"{TABLE}"'


def upgrade() -> None:
    with op.batch_alter_table(TABLE, schema=_schema()) as batch:
        batch.add_column(sa.Column("ats_board_token", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("ats_board_url", sa.String(length=500), nullable=True))

    table = _qualified()
    # Same rule as ``app.models.company.normalize_ats_type``: upper case, no separators,
    # blank -> NULL, and DEMO_ATS keeps its underscore.
    op.execute(f"UPDATE {table} SET ats_type = NULL WHERE ats_type IS NOT NULL AND TRIM(ats_type) = ''")
    op.execute(
        f"UPDATE {table} SET ats_type = 'DEMO_ATS' "
        "WHERE ats_type IS NOT NULL AND REPLACE(REPLACE(UPPER(TRIM(ats_type)), '-', '_'), ' ', '_') = 'DEMO_ATS'"
    )
    op.execute(
        f"UPDATE {table} SET ats_type = REPLACE(REPLACE(REPLACE(UPPER(TRIM(ats_type)), ' ', ''), '-', ''), '_', '') "
        "WHERE ats_type IS NOT NULL AND ats_type <> 'DEMO_ATS'"
    )


def downgrade() -> None:
    with op.batch_alter_table(TABLE, schema=_schema()) as batch:
        batch.drop_column("ats_board_url")
        batch.drop_column("ats_board_token")
