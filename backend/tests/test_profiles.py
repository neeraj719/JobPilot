"""Profile, preference and CandidateContext tests (contract §3, §11)."""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.profiles import service
from app.modules.profiles.schemas import JobPreferenceUpdate, ProfileUpdate

PROFILE = "/api/v1/profile"
PREFERENCES = "/api/v1/preferences/job"


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.core.rate_limit import rate_limiter

    hits = getattr(rate_limiter._backend, "_hits", None)
    if hits is not None:
        hits.clear()
    yield


@pytest.fixture
def user(db: Session):
    from app.modules.auth.service import create_user

    created = create_user(db, "candidate@example.com", "StrongPass123", "Asha Verma")
    db.commit()
    return created


FULL_PROFILE = {
    "phone": "+91 98765 43210",
    "city": "Bangalore",
    "country": "India",
    "linkedin_url": "https://linkedin.com/in/asha",
    "github_url": "https://github.com/asha",
    "portfolio_url": "https://asha.dev",
    "current_designation": "Software Engineer",
    "current_company": "Northwind Labs",
    "years_of_experience": 3.5,
    "current_salary": 800000,
    "summary": "Full stack engineer building React and Node services.",
    "skills": ["reactjs", "Node.js", "postgres"],
    "technologies": ["Docker", "react"],
    "skill_experience": {"ReactJS": 3, "docker": "2 years"},
    "education": [
        {"institution": "IIT Madras", "degree": "B.Tech", "field": "CSE", "start": "2016", "end": "2020"},
        {"institution": "Delhi Public School", "degree": "Class XII", "end": "2016"},
    ],
    "work_authorization": {"IN": True, "US": False},
    "requires_sponsorship": False,
    "willing_to_relocate": True,
}


# --------------------------------------------------------------------------- endpoints


def test_profile_requires_authentication(client: TestClient) -> None:
    assert client.get(PROFILE).status_code == 401
    assert client.put(PROFILE, json={"city": "Pune"}).status_code == 401
    assert client.get(PREFERENCES).status_code == 401


def test_get_profile_returns_completeness_and_missing_fields(auth_client: TestClient) -> None:
    response = auth_client.get(PROFILE)
    assert response.status_code == 200, response.text
    body = response.json()

    # registration copies name + email across, so the profile is not empty
    assert body["full_name"] == "Test User"
    assert body["email"] == "tester@example.com"
    assert 0 < body["completeness"] < 100
    assert "phone" in body["missing_fields"]
    assert "skills" in body["missing_fields"]
    assert "notice_period_days" in body["missing_fields"]
    assert "full_name" not in body["missing_fields"]


def test_update_profile_increases_completeness(auth_client: TestClient) -> None:
    before = auth_client.get(PROFILE).json()["completeness"]

    response = auth_client.put(PROFILE, json=FULL_PROFILE)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["completeness"] > before
    assert body["city"] == "Bangalore"
    assert body["skills"] == ["reactjs", "Node.js", "postgres"]
    assert body["requires_sponsorship"] is False
    assert set(body["missing_fields"]) == {"notice_period_days", "desired_salary"}

    # filling the preference side completes the profile
    auth_client.put(PREFERENCES, json={"notice_period_days": 30, "desired_salary": 1800000})
    completed = auth_client.get(PROFILE).json()
    assert completed["completeness"] == 100
    assert completed["missing_fields"] == []


def test_update_profile_derives_first_and_last_name(auth_client: TestClient) -> None:
    body = auth_client.put(PROFILE, json={"full_name": "Asha Rani Verma"}).json()
    assert body["first_name"] == "Asha"
    assert body["last_name"] == "Rani Verma"


def test_update_profile_derives_full_name_from_parts(auth_client: TestClient) -> None:
    auth_client.put(PROFILE, json={"full_name": None, "first_name": None, "last_name": None})
    body = auth_client.put(PROFILE, json={"first_name": "Ravi", "last_name": "Kumar"}).json()
    assert body["full_name"] == "Ravi Kumar"


def test_job_preferences_round_trip(auth_client: TestClient) -> None:
    defaults = auth_client.get(PREFERENCES).json()
    assert defaults["currency"] == "INR"
    assert defaults["min_match_score"] == 75
    assert defaults["only_posted_within_hours"] == 24

    updated = auth_client.put(
        PREFERENCES,
        json={
            "desired_titles": ["Software Engineer", "Backend Engineer"],
            "preferred_locations": ["Bangalore", "Remote"],
            "work_modes": ["REMOTE", "HYBRID"],
            "employment_types": ["FULL_TIME"],
            "min_salary": 1200000,
            "desired_salary": 1800000,
            "notice_period_days": 30,
            "min_match_score": 80,
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["work_modes"] == ["REMOTE", "HYBRID"]
    assert body["min_match_score"] == 80
    assert auth_client.get(PREFERENCES).json()["desired_salary"] == 1800000


def test_job_preferences_reject_invalid_values(auth_client: TestClient) -> None:
    assert auth_client.put(PREFERENCES, json={"min_match_score": 140}).status_code == 422
    assert auth_client.put(PREFERENCES, json={"work_modes": ["TELEPORT"]}).status_code == 422
    assert auth_client.put(PREFERENCES, json={"notice_period_days": -5}).status_code == 422


# --------------------------------------------------------------------------- candidate context


def test_candidate_context_flat_keys(db: Session, user) -> None:
    service.update_profile(db, user.id, ProfileUpdate(**FULL_PROFILE))
    service.update_job_preference(
        db,
        user.id,
        JobPreferenceUpdate(
            desired_salary=1800000,
            min_salary=1200000,
            notice_period_days=30,
            preferred_locations=["Bangalore", "Remote"],
            work_modes=["REMOTE"],
            desired_titles=["Software Engineer"],
            employment_types=["FULL_TIME"],
        ),
    )
    db.commit()

    ctx = service.build_candidate_context(db, user.id)
    flat = ctx.flat

    assert flat["full_name"] == "Asha Verma"
    assert flat["first_name"] == "Asha"
    assert flat["last_name"] == "Verma"
    assert flat["email"] == "candidate@example.com"
    assert flat["expected_salary"] == 1800000
    assert flat["desired_salary"] == 1800000
    assert flat["min_salary"] == 1200000
    assert flat["currency"] == "INR"
    assert flat["notice_period_days"] == 30
    assert flat["notice_period_text"] == "30 days"
    assert flat["years_of_experience"] == 3.5
    assert flat["work_authorization"] == {"IN": True, "US": False}
    assert flat["requires_sponsorship"] is False
    assert flat["willing_to_relocate"] is True
    assert flat["highest_degree"] == "B.Tech"
    assert flat["university"] == "IIT Madras"
    assert flat["preferred_locations"] == ["Bangalore", "Remote"]
    assert flat["work_modes"] == ["REMOTE"]
    assert flat["desired_titles"] == ["Software Engineer"]
    assert flat["website"] == "https://asha.dev"

    # skills are the normalised union of profile skills + technologies (+ resume)
    assert flat["skills"] == ["React", "Node.js", "PostgreSQL", "Docker"]

    # skill_years:<canonical lowercase skill>
    assert flat["skill_years:react"] == 3.0
    assert flat["skill_years:docker"] == 2.0

    # no resume module data available in this test -> no resume keys at all
    assert ctx.resume is None
    assert ctx.resume_path is None
    assert "resume_file" not in flat

    assert ctx.has("expected_salary")
    assert ctx.skill_years("ReactJS") is None  # lookup is by canonical lowercase key
    assert ctx.skill_years("react") == 3.0


def test_candidate_context_omits_unknown_facts(db: Session, user) -> None:
    ctx = service.build_candidate_context(db, user.id)
    for key in (
        "phone",
        "city",
        "expected_salary",
        "desired_salary",
        "notice_period_days",
        "notice_period_text",
        "requires_sponsorship",
        "work_authorization",
        "resume_file",
    ):
        assert key not in ctx.flat, f"{key} must be absent so consumers ask the user"
    assert ctx.flat["full_name"] == "Asha Verma"
    assert ctx.profile.completeness < 50


def test_candidate_context_expected_salary_falls_back_to_min_salary(db: Session, user) -> None:
    service.update_job_preference(db, user.id, JobPreferenceUpdate(min_salary=900000, notice_period_days=0))
    db.commit()

    flat = service.build_candidate_context(db, user.id).flat
    assert flat["expected_salary"] == 900000
    assert "desired_salary" not in flat
    assert flat["notice_period_text"] == "Immediate"


def test_candidate_context_accepts_unknown_resume_id(db: Session, user) -> None:
    ctx = service.build_candidate_context(db, user.id, resume_id=uuid.uuid4())
    assert ctx.resume is None
    assert ctx.resume_path is None


def test_skill_years_from_resume_requires_dates_and_technologies() -> None:
    parsed = {
        "experience": [
            {"company": "A", "start": "2021-01", "end": "2023-01", "technologies": ["ReactJS", "Node"]},
            {"company": "B", "start": "2020-01", "end": "2021-01", "technologies": ["react"]},
            {"company": "C", "start": "sometime", "end": "later", "technologies": ["Django"]},
            {"company": "D", "start": "2019-01", "technologies": ["Flask"]},
            {"company": "E", "start": "2019-01", "end": "2020-01"},
        ]
    }
    years = service.skill_years_from_resume(parsed)
    assert years["react"] == 3.0
    assert years["node.js"] == 2.0
    assert "django" not in years  # unparsable dates -> never guessed
    assert "flask" not in years  # no end date -> never guessed


def test_profile_skill_years_override_resume_values() -> None:
    assert service.skill_years_from_profile({"ReactJS": 4, "K8s": "5 years", "bogus": None}) == {
        "react": 4.0,
        "kubernetes": 5.0,
    }


def test_candidate_context_to_prompt_dict_is_compact(db: Session, user) -> None:
    service.update_profile(
        db,
        user.id,
        ProfileUpdate(**{**FULL_PROFILE, "summary": "Lorem ipsum dolor sit amet. " * 60}),
    )
    service.update_job_preference(db, user.id, JobPreferenceUpdate(desired_salary=1800000, notice_period_days=30))
    db.commit()

    payload = service.candidate_context_to_prompt_dict(service.build_candidate_context(db, user.id))
    encoded = json.dumps(payload)
    assert len(encoded) <= 2000
    assert payload["full_name"] == "Asha Verma"
    assert payload["expected_salary"] == 1800000
    assert payload["notice_period"] == "30 days"
    assert payload["has_resume"] is False


def test_candidate_context_merges_the_default_resume(db: Session, user, tmp_path) -> None:
    """Integration with the resumes module - skipped while that module is unavailable."""
    pytest.importorskip("app.modules.resumes.service", reason="resumes module not implemented yet")

    from app.models.enums import ResumeParseStatus
    from app.models.resume import Resume

    resume_file = tmp_path / "resume.pdf"
    resume_file.write_bytes(b"%PDF-1.4 test")
    db.add(
        Resume(
            user_id=user.id,
            name="SDE Resume",
            is_default=True,
            file_path=str(resume_file),
            original_filename="resume.pdf",
            mime_type="application/pdf",
            size_bytes=resume_file.stat().st_size,
            parse_status=ResumeParseStatus.PARSED,
            parsed_data={
                "skills": ["Kubernetes", "react"],
                "summary": "Parsed resume summary",
                "total_experience_years": 4.0,
                "experience": [
                    {"company": "A", "start": "2021-01", "end": "2023-01", "technologies": ["Kubernetes"]},
                ],
                "education": [{"institution": "NIT Trichy", "degree": "B.E.", "end": "2019"}],
            },
        )
    )
    db.commit()

    ctx = service.build_candidate_context(db, user.id)
    assert ctx.resume is not None
    assert ctx.resume_path == str(resume_file.resolve())
    assert ctx.flat["resume_file"] == ctx.resume_path
    assert ctx.flat["skills"] == ["Kubernetes", "React"]
    assert ctx.flat["summary"] == "Parsed resume summary"
    assert ctx.flat["years_of_experience"] == 4.0
    assert ctx.flat["highest_degree"] == "B.E."
    assert ctx.flat["skill_years:kubernetes"] == 2.0


def test_get_or_create_helpers_are_idempotent(db: Session, user) -> None:
    first = service.get_or_create_profile(db, user.id)
    assert service.get_or_create_profile(db, user.id).id == first.id
    pref = service.get_or_create_job_preference(db, user.id)
    assert service.get_or_create_job_preference(db, user.id).id == pref.id
