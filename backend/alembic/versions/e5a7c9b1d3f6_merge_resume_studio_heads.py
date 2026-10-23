"""merge resume studio heads: ATS optimizer + AI provider settings

The ATS optimizer (``b4d6f8a0c2e4``) and the AI provider settings (``c7e9b1d3f5a7``) were
built in parallel on top of the resume studio base (``a9c3e5b7d1f0``). They touch disjoint
tables, so the merge itself changes nothing; it only gives Alembic a single head again.

Revision ID: e5a7c9b1d3f6
Revises: b4d6f8a0c2e4, c7e9b1d3f5a7
Create Date: 2026-10-23
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'e5a7c9b1d3f6'
down_revision: Union[str, Sequence[str], None] = ('b4d6f8a0c2e4', 'c7e9b1d3f5a7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
