"""ai model choice: ``model_prompt_mode`` on AI settings, ``source`` on AI usage events

"Which model should process this?" — when a user has two or more usable AI models, every AI
action asks which one to use for that run (``app.modules.ai.choice``). Two additive columns:

``master.ai_provider_settings.model_prompt_mode``
  ``String(10)``, NOT NULL, server default ``'ask'``: ``ask`` (the UI asks before each AI run
  when more than one model is usable) or ``default`` (always use the routing, never ask).
  Existing rows become ``ask``.
``transaction.ai_usage_events.source``
  ``String(20)``, nullable: how the model of the call was chosen — ``per_run`` (picked for
  this run), ``task_override``, ``user_default``, ``server_default`` or ``fallback``.
  Historic rows stay ``NULL``.

Nothing else changes. Runs unchanged on SQLite through ``batch_alter_table`` (schema names
resolve per dialect).

Revision ID: e6f8a0b2c4d7
Revises: f6b8d0c2e4a7
Create Date: 2026-10-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e6f8a0b2c4d7'
down_revision: Union[str, None] = 'f6b8d0c2e4a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MASTER = "master"
TRANSACTION = "transaction"
SETTINGS = "ai_provider_settings"
USAGE = "ai_usage_events"


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _schema(name: str) -> str | None:
    """The named schema on PostgreSQL, ``None`` on SQLite, which has no schemas."""
    return None if _sqlite() else name


def upgrade() -> None:
    with op.batch_alter_table(SETTINGS, schema=_schema(MASTER)) as batch:
        batch.add_column(sa.Column("model_prompt_mode", sa.String(length=10), server_default="ask", nullable=False))
    with op.batch_alter_table(USAGE, schema=_schema(TRANSACTION)) as batch:
        batch.add_column(sa.Column("source", sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table(USAGE, schema=_schema(TRANSACTION)) as batch:
        batch.drop_column("source")
    with op.batch_alter_table(SETTINGS, schema=_schema(MASTER)) as batch:
        batch.drop_column("model_prompt_mode")
