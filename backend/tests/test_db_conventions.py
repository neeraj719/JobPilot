"""The database conventions, enforced as tests rather than as review comments.

Five rules are checked here:

* every table carries the seven standard columns — a uuid ``id``, the database-owned
  ``created_at``/``updated_at`` pair, the ``created_by``/``updated_by`` audit pair and
  ``is_active``/``deleted_at`` — and every link between tables is a uuid foreign key;
* deleting is soft, and the global ORM filter hides tombstones from ``select()``,
  ``Session.get`` and relationship loads alike — with ``include_deleted=True`` as the
  only way past it;
* the keys a user can delete and re-create are partial unique indexes, so re-creating
  what you just deleted works;
* roles live in ``master.roles`` and are granted through the ``master.user_roles``
  junction, with ``User.role`` kept as a derived view for every existing call site;
* the two timestamps belong to the **database**: a server default fills them, a trigger
  bumps ``updated_at`` on any real UPDATE (including one the ORM never sees) and leaves
  a no-op alone, and the acting user is stamped into ``created_by``/``updated_by``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import DateTime, Uuid, inspect, select, text
from sqlalchemy.orm import Session

from app.core.actor import actor_context
from app.core.database import soft_delete
from app.core.security import create_access_token
from app.models import Base
from app.models.enums import CompanyPriority, JobSourceType, UserRole
from app.models.profile import CompanyPreference, UserProfile
from app.models.resume import Resume
from app.models.user import DEFAULT_ROLES, Role, User, UserRoleAssignment
from app.modules.auth import service as auth_service

PREFERENCES = "/api/v1/companies/preferences"


@pytest.fixture
def user(db: Session) -> User:
    created = auth_service.create_user(db, "conventions@example.com", "StrongPass123", "Convention Tester")
    db.commit()
    return created


@pytest.fixture
def api(client: TestClient, user: User) -> TestClient:
    client.headers.update({"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"})
    return client


# --------------------------------------------------------------------------- shape


def test_every_table_has_id_is_active_and_deleted_at() -> None:
    tables = Base.metadata.sorted_tables
    assert len(tables) == 38
    for table in tables:
        assert "id" in table.c, f"{table.fullname} has no id"
        assert isinstance(table.c.id.type, Uuid), f"{table.fullname}.id is not a uuid"
        assert list(table.primary_key.columns) == [table.c.id], f"{table.fullname} is not keyed on id alone"
        assert "is_active" in table.c, f"{table.fullname} has no is_active"
        assert not table.c.is_active.nullable
        assert "deleted_at" in table.c, f"{table.fullname} has no deleted_at"
        assert table.c.deleted_at.nullable


def test_every_foreign_key_is_a_uuid() -> None:
    """Rule 4 of the conventions: links are uuid ids, never a name or a composite."""
    seen = 0
    for table in Base.metadata.sorted_tables:
        for fk in table.foreign_keys:
            seen += 1
            assert isinstance(fk.parent.type, Uuid), f"{table.fullname}.{fk.parent.name} is not a uuid"
            assert fk.column.name == "id", f"{table.fullname}.{fk.parent.name} does not point at an id"
    assert seen >= 35


def test_the_two_new_tables_are_there() -> None:
    assert {"master.roles", "master.user_roles"} <= {t.fullname for t in Base.metadata.sorted_tables}


def test_users_no_longer_has_a_role_column() -> None:
    assert "role" not in Base.metadata.tables["master.users"].c


# --------------------------------------------------------------------------- soft delete


def test_soft_delete_sets_both_lifecycle_columns(db: Session, user: User) -> None:
    pref = CompanyPreference(user_id=user.id, company_name="Acme", normalized_name="acme", priority=CompanyPriority.P1)
    db.add(pref)
    db.commit()

    soft_delete(pref)
    db.commit()
    assert pref.deleted_at is not None
    assert pref.is_active is False

    # Idempotent: re-deleting must not move the tombstone's timestamp.
    first = pref.deleted_at
    soft_delete(pref)
    assert pref.deleted_at == first


def test_the_global_filter_hides_tombstones_from_select(db: Session, user: User) -> None:
    pref = CompanyPreference(user_id=user.id, company_name="Acme", normalized_name="acme", priority=CompanyPriority.P1)
    db.add(pref)
    db.commit()
    soft_delete(pref)
    db.commit()
    db.expunge_all()

    assert db.scalars(select(CompanyPreference)).all() == []
    assert db.scalar(select(CompanyPreference).where(CompanyPreference.id == pref.id)) is None


def test_the_global_filter_hides_tombstones_from_session_get(db: Session, user: User) -> None:
    pref = CompanyPreference(user_id=user.id, company_name="Acme", normalized_name="acme", priority=CompanyPriority.P1)
    db.add(pref)
    db.commit()
    soft_delete(pref)
    db.commit()
    db.expunge_all()

    assert db.get(CompanyPreference, pref.id) is None


def test_the_global_filter_hides_tombstones_from_relationship_loads(db: Session, user: User) -> None:
    """Both a lazy collection load and an eager one have to respect the tombstone."""
    live = CompanyPreference(user_id=user.id, company_name="Live", normalized_name="live", priority=CompanyPriority.P1)
    gone = CompanyPreference(user_id=user.id, company_name="Gone", normalized_name="gone", priority=CompanyPriority.P3)
    db.add_all([live, gone])
    db.commit()
    soft_delete(gone)
    db.commit()
    db.expunge_all()

    reloaded = db.get(User, user.id)
    assert [p.company_name for p in reloaded.company_preferences] == ["Live"]

    db.expunge_all()
    from sqlalchemy.orm import selectinload

    eager = db.scalar(select(User).options(selectinload(User.company_preferences)).where(User.id == user.id))
    assert [p.company_name for p in eager.company_preferences] == ["Live"]


def test_include_deleted_is_the_escape_hatch(db: Session, user: User) -> None:
    pref = CompanyPreference(user_id=user.id, company_name="Acme", normalized_name="acme", priority=CompanyPriority.P1)
    db.add(pref)
    db.commit()
    soft_delete(pref)
    db.commit()
    db.expunge_all()

    rows = db.scalars(select(CompanyPreference).execution_options(include_deleted=True)).all()
    assert [row.id for row in rows] == [pref.id]
    assert db.get(CompanyPreference, pref.id, execution_options={"include_deleted": True}) is not None


def test_deleting_a_preference_through_the_api_is_soft(api: TestClient, db: Session, user: User) -> None:
    created = api.post(PREFERENCES, json={"company_name": "Acme Corp", "priority": "P1"}).json()
    assert api.delete(f"{PREFERENCES}/{created['id']}").status_code == 200
    assert api.get(PREFERENCES).json() == []

    db.expunge_all()
    row = db.get(CompanyPreference, uuid.UUID(created["id"]), execution_options={"include_deleted": True})
    assert row is not None and row.deleted_at is not None and row.is_active is False


# --------------------------------------------------------------------------- partial unique indexes


def test_a_deleted_company_priority_can_be_added_again(api: TestClient) -> None:
    """The classic soft-delete trap: the tombstone must not keep the unique key."""
    created = api.post(PREFERENCES, json={"company_name": "Acme Corp", "priority": "P1"}).json()
    assert api.delete(f"{PREFERENCES}/{created['id']}").status_code == 200

    again = api.post(PREFERENCES, json={"company_name": "Acme Corp", "priority": "P3"})
    assert again.status_code in (200, 201), again.text
    assert again.json()["priority"] == "P3"
    assert [p["company_name"] for p in api.get(PREFERENCES).json()] == ["Acme Corp"]


def test_a_deleted_account_frees_its_email_address(client: TestClient, db: Session) -> None:
    payload = {"email": "recycled@example.com", "password": "StrongPass123", "full_name": "First Owner"}
    assert client.post("/api/v1/auth/register", json=payload).status_code in (200, 201)
    first = db.scalars(select(User).where(User.email == "recycled@example.com")).one()
    soft_delete(first)
    db.commit()

    again = client.post("/api/v1/auth/register", json={**payload, "full_name": "Second Owner"})
    assert again.status_code in (200, 201), again.text
    assert again.json()["user"]["full_name"] == "Second Owner"


@pytest.mark.parametrize(
    "table, index_name, columns",
    [
        ("master.users", "uq_users_email_active", ["email"]),
        ("master.company_preferences", "uq_company_pref_user_name_active", ["user_id", "normalized_name"]),
        ("master.connected_accounts", "uq_connected_account_user_source_active", ["user_id", "source"]),
        ("master.browser_sessions", "uq_browser_session_user_source_active", ["user_id", "source"]),
        ("master.roles", "uq_roles_name_active", ["name"]),
        ("master.user_roles", "uq_user_roles_user_role_active", ["user_id", "role_id"]),
        ("master.standing_answers", "uq_standing_answers_user_key_active", ["user_id", "question_key"]),
    ],
)
def test_the_user_deletable_keys_are_partial_unique_indexes(table: str, index_name: str, columns: list[str]) -> None:
    index = next(i for i in Base.metadata.tables[table].indexes if i.name == index_name)
    assert index.unique
    assert [c.name for c in index.columns] == columns
    assert "deleted_at IS NULL" in str(index.dialect_options["postgresql"]["where"])
    assert "deleted_at IS NULL" in str(index.dialect_options["sqlite"]["where"])


def test_keys_nothing_deletes_stay_plain_unique_constraints() -> None:
    """A partial index where it is not needed would only cost a scan."""
    for table, name in (("unified.job_sources", "uq_job_source_external"), ("unified.job_matches", "uq_job_match_job_user"),
                        ("transaction.applications", "uq_application_user_job")):
        assert any(c.name == name for c in Base.metadata.tables[table].constraints), f"{name} should still be a constraint"


def test_the_partial_unique_index_is_live_in_postgresql(db: Session) -> None:
    indexes = inspect(db.get_bind()).get_indexes("company_preferences", schema="master")
    partial = next(i for i in indexes if i["name"] == "uq_company_pref_user_name_active")
    assert partial["unique"]
    assert "deleted_at IS NULL" in str(partial.get("dialect_options", {}).get("postgresql_where", ""))


# --------------------------------------------------------------------------- auth respects tombstones


def test_a_soft_deleted_user_cannot_authenticate(client: TestClient, db: Session) -> None:
    payload = {"email": "tombstoned@example.com", "password": "StrongPass123", "full_name": "Tombstoned"}
    token = client.post("/api/v1/auth/register", json=payload).json()["access_token"]
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    row = db.scalars(select(User).where(User.email == "tombstoned@example.com")).one()
    soft_delete(row)
    db.commit()

    # get_current_user: Session.get returns None because of the global filter.
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    # ...and so does the login path, which looks the user up by email.
    login = client.post("/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]})
    assert login.status_code == 401


def test_an_inactive_user_cannot_authenticate(client: TestClient, db: Session) -> None:
    """``is_active`` remains a separate business switch: disabled, but not deleted."""
    payload = {"email": "disabled@example.com", "password": "StrongPass123", "full_name": "Disabled"}
    token = client.post("/api/v1/auth/register", json=payload).json()["access_token"]

    row = db.scalars(select(User).where(User.email == "disabled@example.com")).one()
    row.is_active = False
    db.commit()
    assert row.deleted_at is None  # not a delete

    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    login = client.post("/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]})
    assert login.status_code == 401
    assert login.json()["error"]["code"] == "account_disabled"


# --------------------------------------------------------------------------- roles / user_roles


def test_the_role_rows_are_reference_data(db: Session) -> None:
    names = {role.name for role in db.scalars(select(Role))}
    assert names == {name for name, _ in DEFAULT_ROLES}


def test_a_new_user_is_mapped_to_the_user_role(db: Session, user: User) -> None:
    assert [role.name for role in user.roles] == ["USER"]
    assert user.role is UserRole.USER
    mappings = db.scalars(select(UserRoleAssignment).where(UserRoleAssignment.user_id == user.id)).all()
    assert len(mappings) == 1
    assert mappings[0].role.name == "USER"


def test_user_read_exposes_both_role_and_roles(client: TestClient) -> None:
    body = client.post(
        "/api/v1/auth/register",
        json={"email": "reader@example.com", "password": "StrongPass123", "full_name": "Reader"},
    ).json()["user"]
    assert body["role"] == "USER"
    assert body["roles"] == ["USER"]


def test_assign_role_makes_the_derived_role_admin(db: Session, user: User) -> None:
    auth_service.assign_role(db, user, UserRole.ADMIN)
    db.commit()
    assert user.role is UserRole.ADMIN
    assert user.role_names == ["ADMIN", "USER"]
    assert user.has_role(UserRole.ADMIN)


def test_assign_role_is_idempotent(db: Session, user: User) -> None:
    auth_service.assign_role(db, user, UserRole.ADMIN)
    auth_service.assign_role(db, user, UserRole.ADMIN)
    db.commit()
    live = db.scalars(select(UserRoleAssignment).where(UserRoleAssignment.user_id == user.id)).all()
    assert len(live) == 2  # USER + ADMIN, not three


def test_revoke_role_tombstones_the_junction_row_and_can_be_undone(db: Session, user: User) -> None:
    auth_service.assign_role(db, user, UserRole.ADMIN)
    db.commit()
    assert auth_service.revoke_role(db, user, UserRole.ADMIN) is True
    db.commit()

    assert user.role is UserRole.USER
    assert user.role_names == ["USER"]

    admin_role = auth_service.get_role(db, UserRole.ADMIN)
    tombstoned = db.scalars(
        select(UserRoleAssignment)
        .where(UserRoleAssignment.user_id == user.id, UserRoleAssignment.role_id == admin_role.id)
        .execution_options(include_deleted=True)
    ).one()
    assert tombstoned.deleted_at is not None and tombstoned.is_active is False

    # The partial unique index is what makes granting it again possible.
    auth_service.assign_role(db, user, UserRole.ADMIN)
    db.commit()
    assert user.role is UserRole.ADMIN
    still_one = db.scalars(
        select(UserRoleAssignment)
        .where(UserRoleAssignment.user_id == user.id, UserRoleAssignment.role_id == admin_role.id)
        .execution_options(include_deleted=True)
    ).all()
    assert len(still_one) == 1


def test_revoke_role_the_user_does_not_hold_is_a_no_op(db: Session, user: User) -> None:
    assert auth_service.revoke_role(db, user, UserRole.ADMIN) is False


def test_require_roles_reads_the_derived_role(db: Session, user: User) -> None:
    from app.core.deps import require_admin
    from app.core.exceptions import ForbiddenError

    guard = require_admin.__wrapped__ if hasattr(require_admin, "__wrapped__") else require_admin
    with pytest.raises(ForbiddenError):
        guard(user=user)

    auth_service.assign_role(db, user, UserRole.ADMIN)
    db.commit()
    assert guard(user=user) is user


def test_resumes_and_sessions_soft_delete_keeps_the_row(db: Session, user: User) -> None:
    """Spot-check that a converted hard delete really leaves the row behind."""
    from app.models.automation import BrowserSession

    session_row = BrowserSession(user_id=user.id, source=JobSourceType.DEMO_ATS)
    resume = Resume(
        user_id=user.id,
        name="CV",
        file_path="/tmp/cv.pdf",
        original_filename="cv.pdf",
        mime_type="application/pdf",
        size_bytes=1,
    )
    db.add_all([session_row, resume])
    db.commit()

    soft_delete(session_row)
    soft_delete(resume)
    db.commit()
    db.expunge_all()

    assert db.scalars(select(BrowserSession)).all() == []
    assert db.scalars(select(Resume)).all() == []
    assert len(db.scalars(select(Resume).execution_options(include_deleted=True)).all()) == 1


# ------------------------------------------- the seven standard columns (rule 6)


STANDARD_COLUMNS = ("id", "created_at", "updated_at", "created_by", "updated_by", "is_active", "deleted_at")


def test_every_table_has_the_seven_standard_columns() -> None:
    users_id = Base.metadata.tables["master.users"].c.id
    for table in Base.metadata.sorted_tables:
        for name in STANDARD_COLUMNS:
            assert name in table.c, f"{table.fullname} has no {name}"

        for name in ("created_at", "updated_at"):
            column = table.c[name]
            resolved = getattr(column.type, "impl", column.type)
            assert isinstance(resolved, DateTime), f"{table.fullname}.{name} is not a timestamp"
            assert resolved.timezone, f"{table.fullname}.{name} is not timezone-aware"
            assert not column.nullable, f"{table.fullname}.{name} must be NOT NULL"

        for name in ("created_by", "updated_by"):
            column = table.c[name]
            assert isinstance(column.type, Uuid), f"{table.fullname}.{name} is not a uuid"
            assert column.nullable, f"{table.fullname}.{name} must be nullable - NULL means a system write"
            assert {fk.column for fk in column.foreign_keys} == {users_id}, f"{table.fullname}.{name} -> master.users.id"
            assert all(fk.ondelete == "SET NULL" for fk in column.foreign_keys), f"{table.fullname}.{name} ON DELETE"


def test_the_two_timestamps_are_the_databases_to_fill() -> None:
    """A server default on both, and no Python-side default or ``onupdate`` on either.

    Two mechanisms would be one too many: the whole point of the convention is that a
    write the ORM never sees still moves ``updated_at``.
    """
    for table in Base.metadata.sorted_tables:
        for name in ("created_at", "updated_at"):
            column = table.c[name]
            assert column.server_default is not None, f"{table.fullname}.{name} has no server default"
            assert column.default is None, f"{table.fullname}.{name} still has a Python-side default"
            assert column.onupdate is None, f"{table.fullname}.{name} still has a Python-side onupdate"
        assert table.c.updated_at.server_onupdate is not None, f"{table.fullname}.updated_at"


def test_the_database_fills_both_timestamps(db: Session, user: User) -> None:
    pref = CompanyPreference(user_id=user.id, company_name="Acme", normalized_name="acme", priority=CompanyPriority.P1)
    # Nothing exists until the INSERT runs: the value is the database to produce, not ours.
    assert pref.created_at is None
    assert pref.updated_at is None

    db.add(pref)
    db.flush()

    assert pref.created_at is not None
    assert pref.updated_at is not None
    assert pref.created_at.tzinfo is not None  # UTCDateTime hands back aware UTC


def test_an_explicit_timestamp_still_wins(db: Session, user: User) -> None:
    """A server default only applies when the INSERT names no value - which is what lets
    ``app/seed.py`` fabricate three weeks of history on past dates."""
    backdated = datetime.now(timezone.utc) - timedelta(days=21)
    pref = CompanyPreference(
        user_id=user.id, company_name="Acme", normalized_name="acme", priority=CompanyPriority.P1, created_at=backdated
    )
    db.add(pref)
    db.flush()
    assert pref.created_at == backdated


# ------------------------------------------- the trigger


def _updated_at_of(db: Session, pref_id: uuid.UUID):
    return db.execute(
        text('SELECT updated_at FROM "master"."company_preferences" WHERE id = :id'), {"id": pref_id}
    ).scalar_one()


def test_a_raw_update_the_orm_never_sees_bumps_updated_at(db: Session, user: User) -> None:
    """The point of the trigger. No ORM involved: psql, a migration or a bulk UPDATE has
    to move ``updated_at`` too, or "last modified" is only a hopeful label."""
    pref = CompanyPreference(user_id=user.id, company_name="Acme", normalized_name="acme", priority=CompanyPriority.P1)
    db.add(pref)
    db.commit()
    before = _updated_at_of(db, pref.id)

    db.execute(text('UPDATE "master"."company_preferences" SET notes = :n WHERE id = :id'), {"n": "x", "id": pref.id})
    db.commit()

    assert _updated_at_of(db, pref.id) > before


def test_a_no_op_update_leaves_updated_at_alone(db: Session, user: User) -> None:
    """The ``WHEN`` guard: a statement that changed nothing did not modify the row."""
    pref = CompanyPreference(
        user_id=user.id, company_name="Acme", normalized_name="acme", priority=CompanyPriority.P1, notes="keep"
    )
    db.add(pref)
    db.commit()
    before = _updated_at_of(db, pref.id)

    db.execute(text('UPDATE "master"."company_preferences" SET notes = notes WHERE id = :id'), {"id": pref.id})
    db.commit()

    assert _updated_at_of(db, pref.id) == before


def test_the_function_and_every_trigger_are_live(db: Session) -> None:
    from app.core.db_triggers import trigger_name

    function = db.execute(
        text(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND p.proname = 'set_updated_at'"
        )
    ).scalar()
    triggers = set(db.execute(text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")).scalars().all())

    assert function == 1, "public.set_updated_at() is missing"
    expected = {trigger_name(table.name) for table in Base.metadata.sorted_tables}
    assert len(expected) == 38
    assert expected <= triggers


# ------------------------------------------- created_by / updated_by


def test_the_request_actor_is_stamped_through_the_api(client: TestClient, db: Session) -> None:
    """Register, then change the profile: both audit columns name the acting user."""
    payload = {"email": "stamped@example.com", "password": "StrongPass123", "full_name": "Stamped"}
    registered = client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code in (200, 201), registered.text
    token = registered.json()["access_token"]
    user_id = uuid.UUID(registered.json()["user"]["id"])

    # The account is its own author - nobody else was there to create it.
    account = db.get(User, user_id)
    assert account.created_by == user_id
    assert account.updated_by == user_id

    update = client.put(
        "/api/v1/profile",
        json={"headline": "Backend engineer"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert update.status_code == 200, update.text

    db.expire_all()
    profile = db.scalars(select(UserProfile).where(UserProfile.user_id == user_id)).one()
    assert profile.created_by == user_id
    assert profile.updated_by == user_id


def test_a_write_with_no_actor_is_a_system_write(db: Session, user: User) -> None:
    """Background work nobody asked for leaves both columns NULL, and that is the
    answer: no user did this."""
    pref = CompanyPreference(user_id=user.id, company_name="Acme", normalized_name="acme", priority=CompanyPriority.P1)
    db.add(pref)
    db.flush()
    assert pref.created_by is None
    assert pref.updated_by is None


def test_background_work_can_name_the_user_it_acts_for(db: Session, user: User) -> None:
    with actor_context(user.id):
        pref = CompanyPreference(user_id=user.id, company_name="Acme", normalized_name="acme", priority=CompanyPriority.P1)
        db.add(pref)
        db.flush()
    assert pref.created_by == user.id
    assert pref.updated_by == user.id


def test_an_explicit_created_by_is_never_overwritten(db: Session, user: User) -> None:
    """The seeder fabricates history and owns the attribution of what it writes."""
    other = auth_service.create_user(db, "author@example.com", "StrongPass123", "Author")
    db.flush()

    with actor_context(user.id):
        pref = CompanyPreference(
            user_id=user.id,
            company_name="Acme",
            normalized_name="acme",
            priority=CompanyPriority.P1,
            created_by=other.id,
        )
        db.add(pref)
        db.flush()

    assert pref.created_by == other.id  # kept
    assert pref.updated_by == user.id  # only the column nobody set is filled in


def test_updated_by_follows_the_next_writer(db: Session, user: User) -> None:
    other = auth_service.create_user(db, "second@example.com", "StrongPass123", "Second")
    db.flush()

    with actor_context(user.id):
        pref = CompanyPreference(user_id=user.id, company_name="Acme", normalized_name="acme", priority=CompanyPriority.P1)
        db.add(pref)
        db.flush()

    with actor_context(other.id):
        pref.notes = "changed"
        db.flush()

    assert pref.created_by == user.id  # unchanged
    assert pref.updated_by == other.id


def test_the_audit_columns_are_not_an_api_field(api: TestClient) -> None:
    """A database-level trail, not a UI feature: nothing leaks them by accident."""
    created = api.post(PREFERENCES, json={"company_name": "Acme Corp", "priority": "P1"}).json()
    assert "created_by" not in created
    assert "updated_by" not in created
