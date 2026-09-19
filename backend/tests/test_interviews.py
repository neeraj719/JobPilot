"""Interviews module tests (CONTRACTS.md section 11, "Interviews")."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.enums import ApplicationStatus, ApplicationType, JobSourceType, WorkMode
from app.models.interview import Interview
from app.models.job import Job, JobSource

API = "/api/v1/interviews"
APPLICATIONS_API = "/api/v1/applications"
JOBS_API = "/api/v1/jobs"


# --------------------------------------------------------------------------- helpers


def make_job(db: Session, *, company_name: str = "Northwind Labs", title: str = "Full Stack Engineer") -> Job:
    from app.modules.companies.service import normalize_company_name

    company = db.scalars(select(Company).where(Company.name == company_name)).first()
    if company is None:
        company = Company(name=company_name, normalized_name=normalize_company_name(company_name), domain="northwindlabs.dev")
        db.add(company)
        db.flush()
    now = datetime.now(timezone.utc)
    job = Job(
        company_id=company.id,
        title=title,
        normalized_title=title.lower(),
        description="React, Node.js and PostgreSQL product work.",
        location="Bangalore, India",
        work_mode=WorkMode.HYBRID,
        required_skills=["React", "Node.js"],
        posted_at=now - timedelta(hours=3),
        canonical_url=f"https://example.test/jobs/{uuid.uuid4().hex[:8]}",
        apply_url=f"https://example.test/apply/{uuid.uuid4().hex[:8]}",
        application_type=ApplicationType.EASY_APPLY,
        dedupe_hash=uuid.uuid4().hex,
    )
    db.add(job)
    db.flush()
    db.add(
        JobSource(
            job_id=job.id,
            source=JobSourceType.LINKEDIN,
            external_id=f"iv-{uuid.uuid4().hex[:10]}",
            url=job.canonical_url,
            apply_url=job.apply_url,
            application_type=ApplicationType.EASY_APPLY,
            discovered_at=now,
            last_seen_at=now,
        )
    )
    db.commit()
    return job


@pytest.fixture
def ready_client(auth_client: TestClient) -> TestClient:
    r = auth_client.put(
        "/api/v1/profile",
        json={
            "full_name": "Aarav Sharma",
            "city": "Bangalore",
            "years_of_experience": 2.0,
            "skills": ["React", "Node.js", "TypeScript"],
            "current_designation": "Software Engineer",
        },
    )
    assert r.status_code == 200, r.text
    return auth_client


@pytest.fixture
def application_id(ready_client: TestClient, db: Session) -> str:
    job = make_job(db)
    queued = ready_client.post(f"{JOBS_API}/{job.id}/queue")
    assert queued.status_code in (200, 201), queued.text
    return queued.json()["id"]


# --------------------------------------------------------------------------- CRUD


def test_create_list_and_patch_interview(ready_client: TestClient, application_id: str):
    when = datetime.now(timezone.utc) + timedelta(days=3)
    created = ready_client.post(
        API,
        json={
            "application_id": application_id,
            "interview_type": "TECHNICAL",
            "scheduled_at": when.isoformat(),
            "duration_minutes": 60,
            "location_or_link": "https://meet.example.test/abc",
            "interviewer": "Meera Iyer",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["interview_type"] == "TECHNICAL"
    assert body["status"] == "SCHEDULED"
    assert body["company_name"] == "Northwind Labs"
    assert body["job_title"] == "Full Stack Engineer"
    interview_id = body["id"]

    listed = ready_client.get(API).json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == interview_id

    filtered = ready_client.get(API, params={"application_id": application_id}).json()
    assert filtered["total"] == 1

    patched = ready_client.patch(f"{API}/{interview_id}", json={"status": "COMPLETED", "outcome": "PASSED", "notes": "Went well"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["status"] == "COMPLETED"
    assert patched.json()["outcome"] == "PASSED"


def test_upcoming_filter_excludes_past_and_completed(ready_client: TestClient, application_id: str):
    past = datetime.now(timezone.utc) - timedelta(days=2)
    future = datetime.now(timezone.utc) + timedelta(days=2)
    later = datetime.now(timezone.utc) + timedelta(days=9)

    for scheduled in (past, later, future):
        r = ready_client.post(API, json={"application_id": application_id, "interview_type": "HR", "scheduled_at": scheduled.isoformat()})
        assert r.status_code == 201, r.text
    done = ready_client.post(
        API,
        json={"application_id": application_id, "interview_type": "PHONE_SCREEN", "scheduled_at": future.isoformat()},
    ).json()
    ready_client.patch(f"{API}/{done['id']}", json={"status": "COMPLETED"})

    upcoming = ready_client.get(API, params={"upcoming": True}).json()
    assert upcoming["total"] == 2
    # soonest first
    scheduled_times = [item["scheduled_at"] for item in upcoming["items"]]
    assert scheduled_times == sorted(scheduled_times)

    assert ready_client.get(API).json()["total"] == 4


def test_delete_interview(ready_client: TestClient, application_id: str, db: Session):
    created = ready_client.post(API, json={"application_id": application_id, "interview_type": "HR"}).json()
    assert ready_client.delete(f"{API}/{created['id']}").status_code == 204
    db.expire_all()
    assert db.get(Interview, uuid.UUID(created["id"])) is None
    assert ready_client.get(f"{API}/{created['id']}").status_code == 404


# --------------------------------------------------------------------------- prep


def test_prep_populates_prep_material(ready_client: TestClient, application_id: str, db: Session):
    created = ready_client.post(API, json={"application_id": application_id, "interview_type": "TECHNICAL"}).json()
    assert created["prep_material"] == {}

    prepped = ready_client.post(f"{API}/{created['id']}/prep")
    assert prepped.status_code == 200, prepped.text
    material = prepped.json()["prep_material"]
    for bucket in ("technical", "behavioral", "company_specific", "job_specific", "resume_based"):
        assert bucket in material, f"{bucket} missing from {sorted(material)}"
    assert material["technical"], "the mock provider must produce technical questions"
    assert material["generated_at"]

    db.expire_all()
    stored = db.get(Interview, uuid.UUID(created["id"]))
    assert stored.prep_material["technical"] == material["technical"]

    logs = ready_client.get("/api/v1/audit", params={"application_id": application_id, "page_size": 100}).json()["items"]
    assert "interview.prep_generated" in {row["action"] for row in logs}


# --------------------------------------------------------------------------- scoping


def test_interviews_are_scoped_to_their_owner(ready_client: TestClient, application_id: str, client: TestClient):
    created = ready_client.post(API, json={"application_id": application_id, "interview_type": "HR"}).json()

    other = client.post(
        "/api/v1/auth/register",
        json={"email": "nosy@example.com", "password": "StrongPass123!", "full_name": "Nosy Person"},
    )
    assert other.status_code in (200, 201), other.text
    headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    assert client.get(API, headers=headers).json()["total"] == 0
    assert client.get(f"{API}/{created['id']}", headers=headers).status_code == 404
    assert client.post(f"{API}/{created['id']}/prep", headers=headers).status_code == 404
    assert client.delete(f"{API}/{created['id']}", headers=headers).status_code == 404
    assert client.post(
        API,
        json={"application_id": application_id, "interview_type": "HR"},
        headers=headers,
    ).status_code == 404


def test_status_change_to_interview_is_visible_in_the_interviews_list(ready_client: TestClient, application_id: str):
    r = ready_client.patch(f"{APPLICATIONS_API}/{application_id}/status", json={"status": ApplicationStatus.INTERVIEW.value})
    assert r.status_code == 200, r.text

    listed = ready_client.get(API).json()
    assert listed["total"] == 1
    assert listed["items"][0]["interview_type"] == "OTHER"
    assert listed["items"][0]["scheduled_at"] is None
    assert listed["items"][0]["application_id"] == application_id

    # The placeholder round is "upcoming" until it is scheduled or completed.
    assert ready_client.get(API, params={"upcoming": True}).json()["total"] == 1
