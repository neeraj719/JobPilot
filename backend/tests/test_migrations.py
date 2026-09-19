"""The Alembic migration chain must reproduce ``Base.metadata`` exactly.

``alembic upgrade head`` is executed programmatically against a throw-away SQLite file and
the resulting schema is diffed against the models with ``alembic.autogenerate.compare_metadata``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.models import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]

#: The 25 tables of the JobPilot AI schema.
EXPECTED_TABLES = {
    "users",
    "refresh_tokens",
    "user_profiles",
    "job_preferences",
    "company_preferences",
    "companies",
    "jobs",
    "job_sources",
    "job_matches",
    "resumes",
    "resume_versions",
    "skills",
    "applications",
    "application_answers",
    "application_events",
    "application_documents",
    "interviews",
    "email_integrations",
    "email_messages",
    "automation_configs",
    "automation_runs",
    "connected_accounts",
    "browser_sessions",
    "audit_logs",
    "notifications",
}

#: Differences we deliberately ignore.
#:
#: SQLite has no real ``DateTime``/``Uuid``/``JSON`` types (everything is an affinity), so a
#: reflected column can never match the model type object exactly. ``compare_type=False``
#: already suppresses that, and nothing else is ignored — the assertion below is exact.
ALLOWED_DIFF_KINDS: frozenset[str] = frozenset()


def _config(url: str) -> Config:
    """An Alembic config that does not touch logging (no ini file → no ``fileConfig``)."""
    config = Config()
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _diff_kind(diff: Any) -> str:
    if isinstance(diff, tuple) and diff:
        return str(diff[0])
    if isinstance(diff, list) and diff:  # nested (column level) diffs
        return _diff_kind(diff[0])
    return str(diff)


@pytest.fixture
def migrated(tmp_path, monkeypatch):
    """Run ``alembic upgrade head`` on a fresh SQLite file and yield its URL."""
    db_path = tmp_path / "migration-check.db"
    url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    # alembic/env.py prefers DATABASE_URL over the ini value.
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(_config(url), "head")
    yield url


def test_upgrade_creates_every_table(migrated: str) -> None:
    engine = create_engine(migrated)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert EXPECTED_TABLES <= tables
    assert "alembic_version" in tables
    assert len(EXPECTED_TABLES) == 25


def test_migration_matches_models(migrated: str) -> None:
    engine = create_engine(migrated)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={"compare_type": False, "compare_server_default": False, "target_metadata": Base.metadata},
            )
            diffs = list(compare_metadata(context, Base.metadata))
    finally:
        engine.dispose()
    unexpected = [d for d in diffs if _diff_kind(d) not in ALLOWED_DIFF_KINDS]
    assert unexpected == [], f"schema drift between the migration and the models: {unexpected}"


def test_indexes_and_unique_constraints(migrated: str) -> None:
    engine = create_engine(migrated)
    try:
        inspector = inspect(engine)
        application_indexes = {index["name"] for index in inspector.get_indexes("applications")}
        job_source_uniques = {
            constraint["name"] for constraint in inspector.get_unique_constraints("job_sources")
        }
        match_uniques = {constraint["name"] for constraint in inspector.get_unique_constraints("job_matches")}
    finally:
        engine.dispose()
    assert {"ix_applications_user_id", "ix_applications_status", "ix_applications_applied_at"} <= application_indexes
    assert "uq_job_source_external" in job_source_uniques
    assert "uq_job_match_job_user" in match_uniques


def test_downgrade_removes_every_table(migrated: str) -> None:
    command.downgrade(_config(migrated), "base")
    engine = create_engine(migrated)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert not (EXPECTED_TABLES & tables)
