"""move the 25 tables out of public into five named schemas

``public`` was only ever the default, not a decision. The tables now sit in five
schemas that describe how the data behaves rather than what feature owns it:

``master``       slowly-changing reference and ownership rows (11 tables)
``unified``      the de-duplicated job graph shared across users (3 tables)
``transaction``  the high-churn per-application record (7 tables)
``media``        uploaded and generated documents (3 tables)
``audit``        the append-only trail (1 table)

That buys per-schema grants, per-schema backup/restore granularity and a search_path
that makes accidental cross-domain joins visible in review. ``alembic_version`` stays
in ``public`` so migration bookkeeping is never caught up in a later reshuffle.

The move is metadata-only on PostgreSQL: ``ALTER TABLE ... SET SCHEMA`` rewrites the
catalog entry and carries the table's indexes, constraints and sequences with it, so
no rows are copied. On SQLite there are no schemas at all — the engine and
``alembic/env.py`` map all five to "no schema" — so both directions are a no-op.

Revision ID: 7f3ad1c95b62
Revises: a1c4f7b28e10
Create Date: 2026-09-20
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7f3ad1c95b62'
down_revision: Union[str, None] = 'a1c4f7b28e10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: ``schema -> tables``. Kept as data so upgrade and downgrade cannot drift apart,
#: and so the count (25) can be asserted at a glance.
LAYOUT: dict[str, tuple[str, ...]] = {
    "master": (
        "users",
        "user_profiles",
        "job_preferences",
        "company_preferences",
        "companies",
        "skills",
        "refresh_tokens",
        "browser_sessions",
        "connected_accounts",
        "email_integrations",
        "automation_configs",
    ),
    "unified": (
        "jobs",
        "job_sources",
        "job_matches",
    ),
    "transaction": (
        "applications",
        "application_answers",
        "application_events",
        "interviews",
        "email_messages",
        "notifications",
        "automation_runs",
    ),
    "media": (
        "resumes",
        "resume_versions",
        "application_documents",
    ),
    "audit": (
        "audit_logs",
    ),
}


def _quote(identifier: str) -> str:
    """``transaction`` is a reserved word, so every identifier is quoted."""
    return '"' + identifier.replace('"', '""') + '"'


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return  # SQLite: schemas translate to None, nothing to move.
    for schema, tables in LAYOUT.items():
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {_quote(schema)}")
        for table in tables:
            op.execute(f"ALTER TABLE public.{_quote(table)} SET SCHEMA {_quote(schema)}")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for schema, tables in LAYOUT.items():
        for table in tables:
            op.execute(f"ALTER TABLE {_quote(schema)}.{_quote(table)} SET SCHEMA public")
        op.execute(f"DROP SCHEMA IF EXISTS {_quote(schema)}")
