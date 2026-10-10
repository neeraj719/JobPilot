"""The ``updated_at`` triggers: one definition, used by the migration and by the tests.

``updated_at`` is owned by the database (see :class:`app.models.base.TimestampMixin`),
which means something in the database has to maintain it. That something is one trigger
per table, and this module is the single place its DDL is written.

It lives in ``app/core`` rather than inside the Alembic revision because two callers need
it and they must not drift apart:

* the migration that introduces the convention, which runs against production; and
* ``tests/conftest.py``, which builds its schema from ``Base.metadata.create_all`` rather
  than from the migration chain — triggers are not part of SQLAlchemy metadata, so
  without this call the trigger would exist in production and *not* under test, and the
  test proving "a raw UPDATE bumps ``updated_at``" would pass against nothing.

Nothing here imports a model: a migration must keep working when the models have moved
on, so every caller passes the ``(schema, table)`` pairs it means.

PostgreSQL
----------
One ``public.set_updated_at()`` function, one ``BEFORE UPDATE ... FOR EACH ROW`` trigger
per table named ``trg_<table>_updated_at``. The ``WHEN`` guard is what stops an UPDATE
that changes nothing from moving the timestamp — "last modified" should mean it.

The guard compares the two row *texts* rather than the rows themselves. The obvious
``OLD.* IS DISTINCT FROM NEW.*`` looks right and is a trap: row comparison compares field
by field and 20 of the 27 tables carry a ``json`` column, which has no equality operator.
It therefore works only until the compared rows are equal up to that column — i.e. it
raises ``could not identify an equality operator for type json`` on exactly the no-op
update the guard exists for. ``OLD::text IS DISTINCT FROM NEW::text`` has no such hole.

SQLite
------
SQLite has no ``BEFORE UPDATE ... SET`` that can rewrite ``NEW``, so the trigger is an
``AFTER UPDATE`` that writes the row again. ``WHEN NEW.updated_at IS OLD.updated_at`` is
what stops that inner UPDATE from re-firing the trigger forever. SQLite has no schemas
either, so the table names are used bare.

The two dialects are deliberately not identical: SQLite fires on any UPDATE statement,
PostgreSQL only when the row really changed. Nothing in JobPilot runs on SQLite except a
no-Docker local demo, and the alternative — restating all seven columns per table in the
``WHEN`` clause — would have to be regenerated every time a column is added.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Connection

#: ``trg_<table>_updated_at`` — the trigger name, per table, on both backends.
TRIGGER_NAME = "trg_{table}_updated_at"

#: The PostgreSQL function every trigger calls. ``public`` so there is exactly one of it
#: and no schema search-path surprise.
FUNCTION_NAME = "public.set_updated_at"

CREATE_FUNCTION_SQL = f"""
CREATE OR REPLACE FUNCTION {FUNCTION_NAME}() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$
"""

DROP_FUNCTION_SQL = f"DROP FUNCTION IF EXISTS {FUNCTION_NAME}()"

TableRef = tuple[str | None, str]


def _is_sqlite(connection: Connection) -> bool:
    return connection.dialect.name == "sqlite"


def _qualified(schema: str | None, table: str, *, sqlite: bool) -> str:
    """``"schema"."table"`` on PostgreSQL, ``"table"`` on SQLite, which has no schemas."""
    if sqlite or not schema:
        return f'"{table}"'
    return f'"{schema}"."{table}"'


def trigger_name(table: str) -> str:
    return TRIGGER_NAME.format(table=table)


def create_updated_at_triggers(connection: Connection, tables: Iterable[TableRef]) -> list[str]:
    """Create (or replace) the ``updated_at`` trigger on every table in ``tables``.

    Idempotent: each trigger is dropped first, so re-running is safe. Returns the trigger
    names created, which is what the callers assert on.
    """
    tables = list(tables)
    sqlite = _is_sqlite(connection)
    if not sqlite:
        connection.execute(text(CREATE_FUNCTION_SQL))

    created: list[str] = []
    for schema, table in tables:
        name = trigger_name(table)
        target = _qualified(schema, table, sqlite=sqlite)
        if sqlite:
            connection.execute(text(f'DROP TRIGGER IF EXISTS "{name}"'))
            connection.execute(
                text(
                    f'CREATE TRIGGER "{name}" AFTER UPDATE ON {target} FOR EACH ROW\n'
                    f"WHEN NEW.updated_at IS OLD.updated_at\n"
                    f"BEGIN\n"
                    f"    UPDATE {target} SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;\n"
                    f"END"
                )
            )
        else:
            connection.execute(text(f'DROP TRIGGER IF EXISTS "{name}" ON {target}'))
            connection.execute(
                text(
                    f'CREATE TRIGGER "{name}" BEFORE UPDATE ON {target} FOR EACH ROW\n'
                    f"WHEN (OLD::text IS DISTINCT FROM NEW::text)\n"
                    f"EXECUTE FUNCTION {FUNCTION_NAME}()"
                )
            )
        created.append(name)
    return created


def drop_updated_at_triggers(connection: Connection, tables: Iterable[TableRef], *, drop_function: bool = True) -> None:
    """Remove every trigger created by :func:`create_updated_at_triggers`, and the function."""
    sqlite = _is_sqlite(connection)
    for schema, table in tables:
        name = trigger_name(table)
        if sqlite:
            connection.execute(text(f'DROP TRIGGER IF EXISTS "{name}"'))
        else:
            connection.execute(text(f'DROP TRIGGER IF EXISTS "{name}" ON {_qualified(schema, table, sqlite=False)}'))
    if drop_function and not sqlite:
        connection.execute(text(DROP_FUNCTION_SQL))


def metadata_tables(metadata: object) -> Sequence[TableRef]:
    """``(schema, table)`` for every table in a SQLAlchemy ``MetaData``.

    A convenience for the callers that *do* have the models — the test fixtures — so they
    never hand-maintain a copy of the list. The migration passes its own frozen tuple.
    """
    return [(table.schema, table.name) for table in metadata.sorted_tables]  # type: ignore[attr-defined]
