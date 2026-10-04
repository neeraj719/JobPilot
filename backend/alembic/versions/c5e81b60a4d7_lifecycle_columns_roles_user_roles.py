"""lifecycle columns everywhere, a roles table and the user_roles junction

Three conventions land together because they are one decision about how every JobPilot
table is shaped.

1. **``is_active`` + ``deleted_at`` on all 25 existing tables** (and on the two created
   here, so 27 afterwards). ``is_active`` is the business switch — disabled user, closed
   job, paused integration — and already existed on ``users`` and ``jobs``; those two
   only gain the tombstone and the server default the mixin now declares. ``deleted_at``
   is the soft-delete tombstone and is new everywhere. Backfill is implicit: the column
   arrives ``NOT NULL DEFAULT true`` / ``NULL``, so every existing row reads as a live,
   active row, which is exactly what it was.

2. **``master.roles`` + ``master.user_roles`` replace ``users.role``.** The enum column
   could hold one value and adding a role meant a migration. The rows here are the
   authority, the link table carries the grant, and ``User.role`` is now a Python
   property deriving the most privileged name, so nothing that reads a role changed. The
   two role rows are inserted by this migration rather than by the seeder, so a freshly
   migrated database is immediately usable. ``user_roles`` — not ``user_roles`` — is
   also where future per-user links (``team_id``, ``org_id``) will go.

3. **Partial unique indexes where soft delete and UNIQUE would collide.** A tombstoned
   row keeps occupying its unique key, so deleting a company priority and adding the same
   company back would fail on the old constraint. Every key a user can delete and
   legitimately re-create becomes ``UNIQUE ... WHERE deleted_at IS NULL``:
   ``users.email``, ``company_preferences(user_id, normalized_name)``,
   ``connected_accounts(user_id, source)``, ``browser_sessions(user_id, source)`` and the
   two new tables. Keys nothing deletes (``job_sources``, ``job_matches``,
   ``applications``, ``email_messages``, ``user_profiles.user_id`` …) stay plain
   constraints — a partial index there would only cost a scan and buy nothing.

Runs on PostgreSQL and on SQLite. SQLite has no schemas (the engine and ``alembic/env.py``
map all five to "no schema") and cannot drop a column or a constraint in place, so the
schema names are resolved per dialect and every destructive step goes through
``batch_alter_table``, which on PostgreSQL is a plain ``ALTER TABLE``.

Revision ID: c5e81b60a4d7
Revises: 7f3ad1c95b62
Create Date: 2026-10-04
"""
from datetime import datetime, timezone
from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c5e81b60a4d7'
down_revision: Union[str, None] = '7f3ad1c95b62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: Every table that existed before this revision, as ``(schema, table)``. Kept as data so
#: upgrade and downgrade cannot drift, and so the count is checkable at a glance.
EXISTING_TABLES: tuple[tuple[str, str], ...] = (
    ("master", "users"),
    ("master", "user_profiles"),
    ("master", "job_preferences"),
    ("master", "company_preferences"),
    ("master", "companies"),
    ("master", "skills"),
    ("master", "refresh_tokens"),
    ("master", "browser_sessions"),
    ("master", "connected_accounts"),
    ("master", "email_integrations"),
    ("master", "automation_configs"),
    ("unified", "jobs"),
    ("unified", "job_sources"),
    ("unified", "job_matches"),
    ("transaction", "applications"),
    ("transaction", "application_answers"),
    ("transaction", "application_events"),
    ("transaction", "interviews"),
    ("transaction", "email_messages"),
    ("transaction", "automation_runs"),
    ("transaction", "notifications"),
    ("media", "resumes"),
    ("media", "resume_versions"),
    ("media", "application_documents"),
    ("audit", "audit_logs"),
)
assert len(EXISTING_TABLES) == 25

#: The two tables that already carry ``is_active`` — they only need the tombstone.
ALREADY_ACTIVE: frozenset[tuple[str, str]] = frozenset({("master", "users"), ("unified", "jobs")})

#: The two roles every database starts with. Mirrors ``app.models.user.DEFAULT_ROLES``;
#: a migration must not import the models, which move on while it stays frozen.
DEFAULT_ROLES: tuple[tuple[str, str], ...] = (
    ("USER", "Standard JobPilot account"),
    ("ADMIN", "Full administrative access"),
)

#: ``(schema, table, old constraint name, new partial index name, columns)``.
PARTIAL_UNIQUES: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    ("master", "company_preferences", "uq_company_pref_user_name", "uq_company_pref_user_name_active",
     ("user_id", "normalized_name")),
    ("master", "connected_accounts", "uq_connected_account_user_source", "uq_connected_account_user_source_active",
     ("user_id", "source")),
    ("master", "browser_sessions", "uq_browser_session_user_source", "uq_browser_session_user_source_active",
     ("user_id", "source")),
)

NOT_DELETED = "deleted_at IS NULL"


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _schema(name: str) -> str | None:
    """The real schema on PostgreSQL, ``None`` on SQLite, which has none.

    Reflection (which ``batch_alter_table`` relies on) does not go through the engine's
    ``schema_translate_map``, so the translation has to happen here rather than being
    left to the connection.
    """
    return None if _sqlite() else name


def _where() -> dict[str, sa.sql.elements.TextClause]:
    """Dialect keywords making an index partial on "not deleted", for this backend."""
    key = "sqlite_where" if _sqlite() else "postgresql_where"
    return {key: sa.text(NOT_DELETED)}


def _lite_table(schema: str, name: str, *columns: sa.Column) -> sa.Table:
    """A minimal typed ``Table`` for data DML inside the migration.

    Typed columns matter: a ``uuid.UUID`` handed to raw SQL is adapted by psycopg but
    rejected by the sqlite3 driver. Going through SQLAlchemy's ``Uuid`` type makes the
    same statement work on both.
    """
    return sa.Table(name, sa.MetaData(), *columns, schema=_schema(schema))


def _roles_table() -> sa.Table:
    return _lite_table(
        "master", "roles",
        sa.Column("id", sa.Uuid()),
        sa.Column("name", sa.String(50)),
        sa.Column("description", sa.String(255)),
        sa.Column("is_active", sa.Boolean()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )


def _user_roles_table() -> sa.Table:
    return _lite_table(
        "master", "user_roles",
        sa.Column("id", sa.Uuid()),
        sa.Column("user_id", sa.Uuid()),
        sa.Column("role_id", sa.Uuid()),
        sa.Column("is_active", sa.Boolean()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )


def _users_table(with_role: bool) -> sa.Table:
    columns = [sa.Column("id", sa.Uuid())]
    if with_role:
        columns.append(sa.Column("role", sa.String(20)))
    return _lite_table("master", "users", *columns)


# --------------------------------------------------------------------------- upgrade


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc)

    # 1. lifecycle columns on every existing table ---------------------------------
    for schema, table in EXISTING_TABLES:
        with op.batch_alter_table(table, schema=_schema(schema)) as batch:
            if (schema, table) not in ALREADY_ACTIVE:
                batch.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
            batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    if not _sqlite():
        # ``users`` and ``jobs`` had ``is_active`` without a server default; the mixin
        # declares one, so align them rather than leave two columns subtly different.
        for schema, table in sorted(ALREADY_ACTIVE):
            op.execute(f'ALTER TABLE "{schema}"."{table}" ALTER COLUMN is_active SET DEFAULT true')

    # 2. master.roles, with its two reference rows ---------------------------------
    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema=_schema("master"),
    )
    op.create_index("ix_roles_name", "roles", ["name"], unique=False, schema=_schema("master"))
    op.create_index("uq_roles_name_active", "roles", ["name"], unique=True, schema=_schema("master"), **_where())

    role_ids = {name: uuid4() for name, _ in DEFAULT_ROLES}
    op.bulk_insert(
        _roles_table(),
        [
            {
                "id": role_ids[name],
                "name": name,
                "description": description,
                "is_active": True,
                "deleted_at": None,
                "created_at": now,
                "updated_at": now,
            }
            for name, description in DEFAULT_ROLES
        ],
    )

    # 3. master.user_roles, backfilled from users.role -----------------------------
    op.create_table(
        "user_roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], [_fk("master", "roles")], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], [_fk("master", "users")], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema=_schema("master"),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"], unique=False, schema=_schema("master"))
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"], unique=False, schema=_schema("master"))
    op.create_index(
        "uq_user_roles_user_role_active", "user_roles", ["user_id", "role_id"],
        unique=True, schema=_schema("master"), **_where(),
    )

    users = _users_table(with_role=True)
    rows = conn.execute(sa.select(users.c.id, users.c.role)).fetchall()
    if rows:
        op.bulk_insert(
            _user_roles_table(),
            [
                {
                    "id": uuid4(),
                    "user_id": user_id,
                    "role_id": role_ids.get(str(role) or "USER", role_ids["USER"]),
                    "is_active": True,
                    "deleted_at": None,
                    "created_at": now,
                    "updated_at": now,
                }
                for user_id, role in rows
            ],
        )

    # 4. the enum column goes ------------------------------------------------------
    with op.batch_alter_table("users", schema=_schema("master")) as batch:
        batch.drop_column("role")

    # 5. unique keys a user can re-create become partial ---------------------------
    # ``users.email`` was one unique index; it becomes a plain lookup index plus a
    # partial unique one, so a soft-deleted account stops reserving the address.
    op.drop_index("ix_users_email", table_name="users", schema=_schema("master"))
    op.create_index("ix_users_email", "users", ["email"], unique=False, schema=_schema("master"))
    op.create_index("uq_users_email_active", "users", ["email"], unique=True, schema=_schema("master"), **_where())

    for schema, table, old_name, new_name, columns in PARTIAL_UNIQUES:
        with op.batch_alter_table(table, schema=_schema(schema)) as batch:
            batch.drop_constraint(old_name, type_="unique")
        op.create_index(new_name, table, list(columns), unique=True, schema=_schema(schema), **_where())


# --------------------------------------------------------------------------- downgrade


def downgrade() -> None:
    conn = op.get_bind()

    # 5'. partial indexes back to plain unique constraints -------------------------
    for schema, table, old_name, new_name, columns in PARTIAL_UNIQUES:
        op.drop_index(new_name, table_name=table, schema=_schema(schema))
        with op.batch_alter_table(table, schema=_schema(schema)) as batch:
            batch.create_unique_constraint(old_name, list(columns))

    op.drop_index("uq_users_email_active", table_name="users", schema=_schema("master"))
    op.drop_index("ix_users_email", table_name="users", schema=_schema("master"))
    op.create_index("ix_users_email", "users", ["email"], unique=True, schema=_schema("master"))

    # 4'. users.role comes back, repopulated from the mapping ----------------------
    with op.batch_alter_table("users", schema=_schema("master")) as batch:
        batch.add_column(
            sa.Column(
                "role",
                sa.Enum("USER", "ADMIN", name="userrole", native_enum=False, length=20),
                nullable=False,
                server_default="USER",
            )
        )
    mapping = _user_roles_table()
    roles = _roles_table()
    admins = conn.execute(
        sa.select(mapping.c.user_id)
        .select_from(mapping.join(roles, mapping.c.role_id == roles.c.id))
        .where(roles.c.name == "ADMIN", mapping.c.deleted_at.is_(None))
    ).scalars().all()
    if admins:
        users = _users_table(with_role=True)
        conn.execute(sa.update(users).where(users.c.id.in_(admins)).values(role="ADMIN"))
    with op.batch_alter_table("users", schema=_schema("master")) as batch:
        batch.alter_column("role", server_default=None)

    # 3'. / 2'. the two tables go --------------------------------------------------
    op.drop_index("uq_user_roles_user_role_active", table_name="user_roles", schema=_schema("master"))
    op.drop_index("ix_user_roles_role_id", table_name="user_roles", schema=_schema("master"))
    op.drop_index("ix_user_roles_user_id", table_name="user_roles", schema=_schema("master"))
    op.drop_table("user_roles", schema=_schema("master"))
    op.drop_index("uq_roles_name_active", table_name="roles", schema=_schema("master"))
    op.drop_index("ix_roles_name", table_name="roles", schema=_schema("master"))
    op.drop_table("roles", schema=_schema("master"))

    # 1'. lifecycle columns go (``users``/``jobs`` keep the ``is_active`` they had) --
    if not _sqlite():
        for schema, table in sorted(ALREADY_ACTIVE):
            op.execute(f'ALTER TABLE "{schema}"."{table}" ALTER COLUMN is_active DROP DEFAULT')
    for schema, table in reversed(EXISTING_TABLES):
        with op.batch_alter_table(table, schema=_schema(schema)) as batch:
            batch.drop_column("deleted_at")
            if (schema, table) not in ALREADY_ACTIVE:
                batch.drop_column("is_active")


def _fk(schema: str, table: str) -> str:
    """``"master.users.id"`` on PostgreSQL, ``"users.id"`` on SQLite."""
    prefix = "" if _sqlite() else f"{schema}."
    return f"{prefix}{table}.id"
