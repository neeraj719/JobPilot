from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.models import SQLITE_SCHEMA_TRANSLATE_MAP, Base  # noqa: F401 — imports all models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

target_metadata = Base.metadata

#: ``alembic_version`` stays in the default schema so the bookkeeping table is never
#: caught up in a future schema reshuffle. ``None`` *is* that schema (``public`` on
#: PostgreSQL, the single namespace on SQLite) and, unlike the literal string "public",
#: it also matches how the inspector reports the default schema — which is what lets
#: ``--autogenerate`` recognise the version table and leave it alone instead of
#: proposing to drop it (alembic compares ``(schema, name)`` and reflects the default
#: schema as ``None``).
VERSION_TABLE_SCHEMA = None


def _is_sqlite(url: str | None) -> bool:
    return bool(url) and url.startswith("sqlite")


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    sqlite = _is_sqlite(url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        include_schemas=not sqlite,
        version_table_schema=VERSION_TABLE_SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        sqlite = connection.dialect.name == "sqlite"
        if sqlite:
            # SQLite has no schemas: collapse all five model schemas to "no schema"
            # so the very same migrations run unchanged against a local dev.db.
            connection = connection.execution_options(schema_translate_map=SQLITE_SCHEMA_TRANSLATE_MAP)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=sqlite,
            include_schemas=not sqlite,
            version_table_schema=VERSION_TABLE_SCHEMA,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
