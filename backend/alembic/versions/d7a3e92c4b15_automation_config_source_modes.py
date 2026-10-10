"""per-source apply mode on automation_configs

Adds ``master.automation_configs.source_modes``: a JSON map of job source → apply mode
(``AUTO_APPLY`` | ``DISCOVER_ONLY``). It lets the user say "discover LinkedIn jobs but
never apply there" per source, replacing the pipeline rule that let the browser run for
the demo ATS only. A source with no entry falls back to the adapter's
``supports_auto_apply`` flag, so the column arrives as an empty object and every
existing row keeps behaving exactly as before.

One additive column, nothing else. Nullable with a server default of ``'{}'`` so the
``ADD COLUMN`` needs no table rewrite on PostgreSQL. Runs unchanged on SQLite: the schema
name is resolved per dialect and the drop goes through ``batch_alter_table``, which is a
plain ``ALTER TABLE`` on PostgreSQL.

Revision ID: d7a3e92c4b15
Revises: c5e81b60a4d7
Create Date: 2026-10-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd7a3e92c4b15'
down_revision: Union[str, None] = 'c5e81b60a4d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "automation_configs"
COLUMN = "source_modes"


def _schema() -> str | None:
    """``master`` on PostgreSQL, ``None`` on SQLite, which has no schemas."""
    return None if op.get_bind().dialect.name == "sqlite" else "master"


def upgrade() -> None:
    with op.batch_alter_table(TABLE, schema=_schema()) as batch:
        batch.add_column(sa.Column(COLUMN, sa.JSON(), nullable=True, server_default=sa.text("'{}'")))


def downgrade() -> None:
    with op.batch_alter_table(TABLE, schema=_schema()) as batch:
        batch.drop_column(COLUMN)
