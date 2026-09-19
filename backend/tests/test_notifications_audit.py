"""Notification + audit endpoint tests (contract §5)."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.models.application import Application
from app.models.automation import AutomationRun
from app.models.base import utcnow
from app.models.enums import Actor, ApplicationStatus, AuditLevel, AutomationRunTrigger, NotificationType
from app.models.job import Job
from app.models.user import User
from app.modules.companies.service import get_or_create_company
from app.modules.notifications.service import notify, unread_count

NOTIFICATIONS = "/api/v1/notifications"
AUDIT = "/api/v1/audit"


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.core.rate_limit import rate_limiter

    hits = getattr(rate_limiter._backend, "_hits", None)
    if hits is not None:
        hits.clear()
    yield


@pytest.fixture
def me(auth_client: TestClient, db: Session) -> User:
    return db.scalars(select(User).where(User.email == "tester@example.com")).one()


@pytest.fixture
def other_user(db: Session) -> User:
    from app.modules.auth.service import create_user

    user = create_user(db, "someone.else@example.com", "StrongPass123", "Someone Else")
    db.commit()
    return user


def _make_application(db: Session, user_id: uuid.UUID) -> Application:
    company = get_or_create_company(db, "Northwind Labs")
    job = Job(
        company_id=company.id,
        title="Software Engineer",
        normalized_title="software engineer",
        description="",
        dedupe_hash=uuid.uuid4().hex,
    )
    db.add(job)
    db.flush()
    application = Application(user_id=user_id, job_id=job.id, status=ApplicationStatus.QUEUED)
    db.add(application)
    db.flush()
    return application


# --------------------------------------------------------------------------- notifications


def test_notify_creates_a_notification(db: Session, me: User) -> None:
    notification = notify(
        db,
        me.id,
        NotificationType.INPUT_REQUIRED,
        "Answer needed",
        body="One question could not be answered",
        link="/applications/123",
        meta={"application_id": "123"},
    )
    db.commit()

    assert notification.id is not None
    assert notification.is_read is False
    assert notification.meta == {"application_id": "123"}
    assert unread_count(db, me.id) == 1


def test_notification_listing_filtering_and_read_flow(auth_client: TestClient, db: Session, me: User) -> None:
    notify(db, me.id, NotificationType.JOB_FOUND, "3 new jobs", meta={"count": 3})
    second = notify(db, me.id, NotificationType.APPLICATION_SUBMITTED, "Applied to Google", link="/applications/1")
    third = notify(db, me.id, NotificationType.REJECTION, "Rejected by Acme")
    third.is_read = True
    db.commit()

    listing = auth_client.get(NOTIFICATIONS)
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["total"] == 3
    assert body["page"] == 1
    first_item = body["items"][0]
    assert set(first_item) == {"id", "type", "title", "body", "link", "is_read", "metadata", "created_at"}
    assert {item["title"] for item in body["items"]} == {"3 new jobs", "Applied to Google", "Rejected by Acme"}
    assert any(item["metadata"] == {"count": 3} for item in body["items"])

    unread = auth_client.get(NOTIFICATIONS, params={"unread_only": True})
    assert unread.json()["total"] == 2
    assert auth_client.get(f"{NOTIFICATIONS}/unread-count").json() == {"count": 2}

    marked = auth_client.post(f"{NOTIFICATIONS}/{second.id}/read")
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True
    assert auth_client.get(f"{NOTIFICATIONS}/unread-count").json()["count"] == 1

    read_all = auth_client.post(f"{NOTIFICATIONS}/read-all")
    assert read_all.status_code == 200
    assert read_all.json() == {"ok": True, "updated": 1}
    assert auth_client.get(f"{NOTIFICATIONS}/unread-count").json()["count"] == 0
    assert auth_client.get(NOTIFICATIONS, params={"unread_only": True}).json()["total"] == 0


def test_notifications_are_scoped_to_the_current_user(auth_client: TestClient, db: Session, me: User, other_user: User) -> None:
    mine = notify(db, me.id, NotificationType.SYSTEM, "Mine")
    theirs = notify(db, other_user.id, NotificationType.SYSTEM, "Theirs")
    db.commit()

    body = auth_client.get(NOTIFICATIONS).json()
    assert [item["title"] for item in body["items"]] == ["Mine"]
    assert auth_client.post(f"{NOTIFICATIONS}/{theirs.id}/read").status_code == 404
    assert auth_client.post(f"{NOTIFICATIONS}/{mine.id}/read").status_code == 200

    db.expire_all()
    assert unread_count(db, other_user.id) == 1


def test_notification_pagination(auth_client: TestClient, db: Session, me: User) -> None:
    for i in range(5):
        notify(db, me.id, NotificationType.SYSTEM, f"Notice {i}")
    db.commit()

    page = auth_client.get(NOTIFICATIONS, params={"page": 2, "page_size": 2}).json()
    assert page["total"] == 5
    assert page["page"] == 2
    assert len(page["items"]) == 2


def test_notifications_require_auth(client: TestClient) -> None:
    assert client.get(NOTIFICATIONS).status_code == 401
    assert client.get(f"{NOTIFICATIONS}/unread-count").status_code == 401
    assert client.post(f"{NOTIFICATIONS}/read-all").status_code == 401


# --------------------------------------------------------------------------- audit


def test_audit_listing_and_filters(auth_client: TestClient, db: Session, me: User, other_user: User) -> None:
    application = _make_application(db, me.id)
    run = AutomationRun(user_id=me.id, trigger=AutomationRunTrigger.MANUAL, started_at=utcnow())
    db.add(run)
    db.flush()
    run_id = run.id

    audit(db, action="job.found", message="Found a job", user_id=me.id, actor=Actor.AUTOMATION)
    audit(
        db,
        action="application.created",
        message="Queued Google SDE",
        user_id=me.id,
        application_id=application.id,
        actor=Actor.AUTOMATION,
        meta={"job": "sde"},
    )
    audit(
        db,
        action="application.failed",
        message="Form changed",
        user_id=me.id,
        application_id=application.id,
        level=AuditLevel.ERROR,
    )
    audit(db, action="automation.run_started", message="Run started", user_id=me.id, automation_run_id=run_id)
    audit(db, action="job.found", message="Not mine", user_id=other_user.id)
    db.commit()

    everything = auth_client.get(AUDIT)
    assert everything.status_code == 200, everything.text
    body = everything.json()
    # the registration audit entry is included, the other user's entry is not
    assert body["total"] == 5
    assert all("Not mine" != item["message"] for item in body["items"])
    sample = body["items"][0]
    assert set(sample) == {
        "id",
        "actor",
        "level",
        "action",
        "message",
        "metadata",
        "application_id",
        "automation_run_id",
        "created_at",
    }

    by_prefix = auth_client.get(AUDIT, params={"action_prefix": "application."}).json()
    assert by_prefix["total"] == 2
    assert {item["action"] for item in by_prefix["items"]} == {"application.created", "application.failed"}
    assert any(item["level"] == "ERROR" for item in by_prefix["items"])
    assert any(item["metadata"] == {"job": "sde"} for item in by_prefix["items"])

    by_application = auth_client.get(AUDIT, params={"application_id": str(application.id)}).json()
    assert by_application["total"] == 2

    by_run = auth_client.get(AUDIT, params={"automation_run_id": str(run_id)}).json()
    assert by_run["total"] == 1
    assert by_run["items"][0]["action"] == "automation.run_started"

    empty = auth_client.get(AUDIT, params={"automation_run_id": str(uuid.uuid4())}).json()
    assert empty["total"] == 0 and empty["items"] == []


def test_audit_pagination_reports_the_full_total(auth_client: TestClient, db: Session, me: User) -> None:
    for i in range(6):
        audit(db, action="automation.step", message=f"step {i}", user_id=me.id)
    db.commit()

    page = auth_client.get(AUDIT, params={"action_prefix": "automation.", "page": 2, "page_size": 4}).json()
    assert page["total"] == 6
    assert page["page"] == 2
    assert len(page["items"]) == 2


def test_audit_requires_auth(client: TestClient) -> None:
    assert client.get(AUDIT).status_code == 401
