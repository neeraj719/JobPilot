"""merge heads: per-run AI model choice + LinkedIn connections

The per-run AI model choice (``e6f8a0b2c4d7``: ``ai_provider_settings.model_prompt_mode``,
``ai_usage_events.source``) and the LinkedIn connection (``d2e4f6a8b0c1``:
``master.linkedin_connections``) were built in parallel on top of the workspace/modules
revision (``f6b8d0c2e4a7``). They touch disjoint tables, so the merge itself changes nothing;
it only gives Alembic a single head again.

Revision ID: f7a9b1c3d5e8
Revises: e6f8a0b2c4d7, d2e4f6a8b0c1
Create Date: 2026-10-24
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'f7a9b1c3d5e8'
down_revision: Union[str, Sequence[str], None] = ('e6f8a0b2c4d7', 'd2e4f6a8b0c1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
