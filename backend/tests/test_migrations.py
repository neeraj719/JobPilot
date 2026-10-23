"""The Alembic migration chain must reproduce ``Base.metadata`` exactly.

``alembic upgrade head`` is executed programmatically against a throw-away **PostgreSQL**
database and the resulting schema is diffed against the models with
``alembic.autogenerate.compare_metadata``.

PostgreSQL is the only backend with real schemas, so it is the only place the five-schema
layout can be checked at all: a SQLite run would see the translated (schema-less) shape
and could never catch a table left behind in ``public``.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from app.models import SCHEMAS, Base

BACKEND_DIR = Path(__file__).resolve().parents[1]

#: ``tests/conftest.py`` has already pinned this to the PostgreSQL test database.
TEST_DATABASE_URL = os.environ["DATABASE_URL"]

#: A database of its own, so upgrade/downgrade can never disturb the suite's own tables.
#: Named after the suite's database, so two suites pointed at different test databases on
#: one server never drop each other's migration database mid-run.
MIGRATION_DATABASE = f"{make_url(TEST_DATABASE_URL).database}_migration_check"

#: The 35 tables of the JobPilot AI schema, as ``schema.table``.
EXPECTED_TABLES = {
    "master.users",
    "master.roles",
    "master.user_roles",
    "master.refresh_tokens",
    "master.user_profiles",
    "master.job_preferences",
    "master.company_preferences",
    "master.companies",
    "master.skills",
    "master.email_integrations",
    "master.automation_configs",
    "master.connected_accounts",
    "master.browser_sessions",
    "master.standing_answers",
    "master.ai_provider_settings",
    "master.ai_provider_credentials",
    "unified.jobs",
    "unified.job_sources",
    "unified.job_matches",
    "media.resumes",
    "media.resume_versions",
    "media.application_documents",
    "media.job_targets",
    "media.job_description_snapshots",
    "media.ats_analyses",
    "media.optimization_suggestions",
    "transaction.applications",
    "transaction.application_answers",
    "transaction.application_events",
    "transaction.interviews",
    "transaction.email_messages",
    "transaction.automation_runs",
    "transaction.notifications",
    "transaction.ai_usage_events",
    "audit.audit_logs",
}

#: Differences we deliberately ignore. None: ``compare_type=False`` already absorbs the
#: type-object identity noise, so the assertion below is exact.
ALLOWED_DIFF_KINDS: frozenset[str] = frozenset()


def _config(url: str) -> Config:
    """An Alembic config that does not touch logging (no ini file → no ``fileConfig``)."""
    config = Config()
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def _diff_kind(diff: Any) -> str:
    if isinstance(diff, tuple) and diff:
        return str(diff[0])
    if isinstance(diff, list) and diff:  # nested (column level) diffs
        return _diff_kind(diff[0])
    return str(diff)


def _recreate_database(url: str) -> None:
    """Drop and re-create the throw-away migration database."""
    admin = create_engine(make_url(url).set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{MIGRATION_DATABASE}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{MIGRATION_DATABASE}"'))
    finally:
        admin.dispose()


@pytest.fixture
def migrated(monkeypatch):
    """Run ``alembic upgrade head`` on a brand-new PostgreSQL database and yield its URL."""
    url = make_url(TEST_DATABASE_URL).set(database=MIGRATION_DATABASE).render_as_string(hide_password=False)
    _recreate_database(url)
    # alembic/env.py prefers DATABASE_URL over the ini value.
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(_config(url), "head")
    yield url


def _named_schema_tables(engine) -> set[str]:
    inspector = inspect(engine)
    return {f"{schema}.{name}" for schema in SCHEMAS for name in inspector.get_table_names(schema=schema)}


def test_upgrade_creates_every_table(migrated: str) -> None:
    engine = create_engine(migrated, poolclass=NullPool)
    try:
        tables = _named_schema_tables(engine)
        public = set(inspect(engine).get_table_names(schema="public"))
    finally:
        engine.dispose()
    assert tables == EXPECTED_TABLES
    assert len(EXPECTED_TABLES) == 35
    # Only Alembic's own bookkeeping is left behind in ``public``.
    assert public == {"alembic_version"}


def test_migration_matches_models(migrated: str) -> None:
    engine = create_engine(migrated, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={
                    "compare_type": False,
                    "compare_server_default": False,
                    "target_metadata": Base.metadata,
                    "include_schemas": True,
                    # ``None`` is the default schema (``public``); see alembic/env.py.
                    "version_table_schema": None,
                },
            )
            diffs = list(compare_metadata(context, Base.metadata))
    finally:
        engine.dispose()
    unexpected = [d for d in diffs if _diff_kind(d) not in ALLOWED_DIFF_KINDS]
    assert unexpected == [], f"schema drift between the migration and the models: {unexpected}"


def test_indexes_and_unique_constraints(migrated: str) -> None:
    """``ALTER TABLE ... SET SCHEMA`` has to carry indexes and constraints along with it."""
    engine = create_engine(migrated, poolclass=NullPool)
    try:
        inspector = inspect(engine)
        application_indexes = {index["name"] for index in inspector.get_indexes("applications", schema="transaction")}
        job_source_uniques = {
            constraint["name"] for constraint in inspector.get_unique_constraints("job_sources", schema="unified")
        }
        match_uniques = {
            constraint["name"] for constraint in inspector.get_unique_constraints("job_matches", schema="unified")
        }
    finally:
        engine.dispose()
    assert {"ix_applications_user_id", "ix_applications_status", "ix_applications_applied_at"} <= application_indexes
    assert "uq_job_source_external" in job_source_uniques
    assert "uq_job_match_job_user" in match_uniques


def test_downgrade_removes_every_table(migrated: str) -> None:
    command.downgrade(_config(migrated), "base")
    engine = create_engine(migrated, poolclass=NullPool)
    try:
        inspector = inspect(engine)
        schemas = set(inspector.get_schema_names())
        public = set(inspector.get_table_names(schema="public"))
    finally:
        engine.dispose()
    # The five schemas go with their tables, and ``public`` is empty again.
    assert not (set(SCHEMAS) & schemas)
    assert public <= {"alembic_version"}
