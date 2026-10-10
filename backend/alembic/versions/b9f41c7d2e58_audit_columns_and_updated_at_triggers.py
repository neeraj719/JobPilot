"""the four audit columns on all 27 tables, with updated_at maintained by the database

Convention 6: every table carries ``created_at``, ``updated_at``, ``created_by`` and
``updated_by`` on top of the ``id`` / ``is_active`` / ``deleted_at`` the previous
revision gave it — seven standard columns, one mixin, no exceptions.

What this revision actually changes, table by table:

* **three tables had neither timestamp** (``master.skills``, ``unified.job_sources``,
  ``transaction.automation_runs``). They get both. ``created_at`` is backfilled from the
  column that already recorded the same fact where there is one — ``discovered_at`` for
  a job source, ``started_at`` for an automation run — rather than from ``now()``, which
  would date three weeks of demo history to the minute the migration ran.
* **seven tables had a bare ``created_at``** with no default and no ``updated_at``
  (``refresh_tokens``, ``resume_versions``, ``application_events``,
  ``application_documents``, ``email_messages``, ``audit_logs``, ``notifications``).
  They gain ``DEFAULT now()`` on ``created_at`` and an ``updated_at`` backfilled from it:
  a row that has never been changed was last changed when it was written.
* **all 27** gain ``created_by`` / ``updated_by``: nullable uuids referencing
  ``master.users.id`` ``ON DELETE SET NULL``. Nullable because ``NULL`` is a real answer
  — a scheduler tick, a migration or a seed run is a system write and should read as
  one — and ``SET NULL`` because the audit trail must not keep a deleted account alive.
  Existing rows therefore read as system writes, which is exactly what they were.
  Deliberately **not** indexed: these are an audit trail, not a query path.
* **all 27** gain a ``trg_<table>_updated_at`` trigger, so ``updated_at`` is maintained
  by the database rather than by the ORM and a hand-written ``UPDATE`` in psql moves it
  too. The DDL lives in ``app/core/db_triggers.py`` because ``tests/conftest.py`` builds
  its schema from ``Base.metadata`` and has to create the same triggers; a trigger that
  existed only in production would make the test proving it meaningless.

Runs on PostgreSQL and on SQLite, with two documented differences on the latter (which
is only ever the no-Docker local demo):

* ``created_by`` / ``updated_by`` are added as plain uuid columns with no foreign key.
  SQLite cannot add a constraint to an existing table without rewriting it, and
  rewriting all 27 would put the partial unique indexes of the previous revision — the
  ones that make soft delete and UNIQUE coexist — through a reflect-and-recreate round
  trip for no benefit. The ten tables that *are* rewritten here (to make a new
  ``updated_at`` ``NOT NULL``) carry no partial index between them.
* the SQLite trigger fires on any UPDATE statement, not only on one that changes
  something — see ``app/core/db_triggers.py`` for why.

Revision ID: b9f41c7d2e58
Revises: d7a3e92c4b15
Create Date: 2026-10-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.db_triggers import create_updated_at_triggers, drop_updated_at_triggers

# revision identifiers, used by Alembic.
revision: str = 'b9f41c7d2e58'
down_revision: Union[str, None] = 'd7a3e92c4b15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: All 27 tables, as ``(schema, table)``. Frozen here rather than read from
#: ``Base.metadata``: a migration must keep doing the same thing when the models move on.
ALL_TABLES: tuple[tuple[str, str], ...] = (
    ("master", "users"),
    ("master", "roles"),
    ("master", "user_roles"),
    ("master", "refresh_tokens"),
    ("master", "user_profiles"),
    ("master", "job_preferences"),
    ("master", "company_preferences"),
    ("master", "companies"),
    ("master", "skills"),
    ("master", "email_integrations"),
    ("master", "automation_configs"),
    ("master", "connected_accounts"),
    ("master", "browser_sessions"),
    ("unified", "jobs"),
    ("unified", "job_sources"),
    ("unified", "job_matches"),
    ("media", "resumes"),
    ("media", "resume_versions"),
    ("media", "application_documents"),
    ("transaction", "applications"),
    ("transaction", "application_answers"),
    ("transaction", "application_events"),
    ("transaction", "interviews"),
    ("transaction", "email_messages"),
    ("transaction", "automation_runs"),
    ("transaction", "notifications"),
    ("audit", "audit_logs"),
)
assert len(ALL_TABLES) == 27

#: Had no ``created_at`` at all.
MISSING_CREATED_AT: tuple[tuple[str, str], ...] = (
    ("master", "skills"),
    ("unified", "job_sources"),
    ("transaction", "automation_runs"),
)

#: Where a truthful ``created_at`` can be recovered from a column already on the row.
CREATED_AT_BACKFILL: dict[tuple[str, str], str] = {
    ("unified", "job_sources"): "discovered_at",
    ("transaction", "automation_runs"): "started_at",
}

#: Had ``created_at NOT NULL`` but no ``DEFAULT``, and no ``updated_at``.
BARE_CREATED_AT: tuple[tuple[str, str], ...] = (
    ("master", "refresh_tokens"),
    ("media", "resume_versions"),
    ("media", "application_documents"),
    ("transaction", "application_events"),
    ("transaction", "email_messages"),
    ("transaction", "notifications"),
    ("audit", "audit_logs"),
)

#: Every table that has to grow an ``updated_at``.
MISSING_UPDATED_AT: tuple[tuple[str, str], ...] = MISSING_CREATED_AT + BARE_CREATED_AT
assert len(MISSING_UPDATED_AT) == 10

TS = sa.DateTime(timezone=True)


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _schema(name: str) -> str | None:
    """The real schema on PostgreSQL, ``None`` on SQLite, which has none."""
    return None if _sqlite() else name


def _qualified(schema: str, table: str) -> str:
    return f'"{table}"' if _sqlite() else f'"{schema}"."{table}"'


def _audit_column(name: str) -> sa.Column:
    """``created_by`` / ``updated_by``, with the foreign key where the backend can take one."""
    if _sqlite():
        return sa.Column(name, sa.Uuid(), nullable=True)
    return sa.Column(name, sa.Uuid(), sa.ForeignKey("master.users.id", ondelete="SET NULL"), nullable=True)


# --------------------------------------------------------------------------- upgrade


def upgrade() -> None:
    conn = op.get_bind()

    # 1. the two timestamps, added nullable so existing rows can be backfilled ------
    for schema, table in MISSING_CREATED_AT:
        op.add_column(table, sa.Column("created_at", TS, nullable=True), schema=_schema(schema))
        source = CREATED_AT_BACKFILL.get((schema, table))
        filler = source if source else ("CURRENT_TIMESTAMP" if _sqlite() else "now()")
        op.execute(f"UPDATE {_qualified(schema, table)} SET created_at = {filler} WHERE created_at IS NULL")

    for schema, table in MISSING_UPDATED_AT:
        op.add_column(table, sa.Column("updated_at", TS, nullable=True), schema=_schema(schema))
        # Never changed since it was written: that is what "last modified" means here.
        op.execute(f"UPDATE {_qualified(schema, table)} SET updated_at = created_at WHERE updated_at IS NULL")

    # 2. ... then tightened to the shape the mixin declares -------------------------
    for schema, table in MISSING_UPDATED_AT:
        columns = ["created_at", "updated_at"] if (schema, table) in MISSING_CREATED_AT else ["updated_at"]
        with op.batch_alter_table(table, schema=_schema(schema)) as batch:
            for column in columns:
                batch.alter_column(column, existing_type=TS, nullable=False, server_default=sa.func.now())

    # 3. the seven pre-existing bare ``created_at`` columns only lacked the default --
    for schema, table in BARE_CREATED_AT:
        with op.batch_alter_table(table, schema=_schema(schema)) as batch:
            batch.alter_column("created_at", existing_type=TS, existing_nullable=False, server_default=sa.func.now())

    # 4. who wrote the row, on every table ------------------------------------------
    for schema, table in ALL_TABLES:
        op.add_column(table, _audit_column("created_by"), schema=_schema(schema))
        op.add_column(table, _audit_column("updated_by"), schema=_schema(schema))

    # 5. and the trigger that makes ``updated_at`` the database's job ---------------
    create_updated_at_triggers(conn, ALL_TABLES)


# --------------------------------------------------------------------------- downgrade


def downgrade() -> None:
    conn = op.get_bind()

    drop_updated_at_triggers(conn, ALL_TABLES)

    for schema, table in ALL_TABLES:
        with op.batch_alter_table(table, schema=_schema(schema)) as batch:
            batch.drop_column("updated_by")
            batch.drop_column("created_by")

    for schema, table in MISSING_UPDATED_AT:
        with op.batch_alter_table(table, schema=_schema(schema)) as batch:
            batch.drop_column("updated_at")

    for schema, table in MISSING_CREATED_AT:
        with op.batch_alter_table(table, schema=_schema(schema)) as batch:
            batch.drop_column("created_at")

    # The seven keep their ``created_at``; they only gave up the default they gained.
    for schema, table in BARE_CREATED_AT:
        with op.batch_alter_table(table, schema=_schema(schema)) as batch:
            batch.alter_column("created_at", existing_type=TS, existing_nullable=False, server_default=None)
