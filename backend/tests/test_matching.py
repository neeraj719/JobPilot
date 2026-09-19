"""Tests for the matching module: pure scoring + persistence + API (§10)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token, hash_password
from app.models.company import Company
from app.models.enums import ApplicationStatus, CompanyPriority, EmploymentType, WorkMode
from app.models.job import Job, JobMatch
from app.models.profile import CompanyPreference, JobPreference, UserProfile
from app.models.resume import Resume
from app.models.user import User
from app.modules.jobs.dedupe import compute_dedupe_hash
from app.modules.matching import scoring, service
from app.modules.matching.scoring import combine, score_experience, score_location, score_salary, score_skills, score_title

API = "/api/v1/matching"


# --------------------------------------------------------------------------- scoring: skills


def test_score_skills_weights_required_over_preferred():
    full, matched, missing = score_skills(["React", "Node.js"], ["Docker"], ["React", "Node.js", "Docker"])
    assert full == 100
    assert set(matched) == {"React", "Node.js", "Docker"}
    assert missing == []

    required_only, _, missing_pref = score_skills(["React", "Node.js"], ["Docker"], ["React", "Node.js"])
    assert required_only == 75  # 0.75 * 1.0 + 0.25 * 0.0
    assert missing_pref == []  # only *required* gaps are reported

    preferred_only, _, missing_req = score_skills(["React", "Node.js"], ["Docker"], ["Docker"])
    assert preferred_only == 25
    assert set(missing_req) == {"React", "Node.js"}


def test_score_skills_reports_missing_required_skills():
    score, matched, missing = score_skills(["React", "Kubernetes", "Go"], [], ["react"])
    assert matched == ["React"]
    assert missing == ["Kubernetes", "Go"]
    assert score == 33


def test_score_skills_uses_aliases():
    score, matched, missing = score_skills(["ReactJS", "NodeJS"], [], ["React", "node.js"])
    assert score == 100 and missing == [] and len(matched) == 2


def test_score_skills_falls_back_to_preferred_then_neutral():
    preferred_only, _, missing = score_skills([], ["Docker", "AWS"], ["Docker"])
    assert preferred_only == 50
    assert missing == ["AWS"]
    assert score_skills([], [], ["React"]) == (60, [], [])


# --------------------------------------------------------------------------- scoring: title


def test_score_title_matches_exactly_and_by_family():
    assert score_title("Software Engineer", ["Software Engineer"]) == 100
    assert score_title("SDE II", ["Software Engineer"]) >= 85
    assert score_title("Sr. Backend Engineer", ["Backend Engineer"]) >= 85
    assert score_title("React Developer", ["Frontend Engineer"]) >= 85


def test_score_title_penalises_unrelated_roles():
    assert score_title("DevOps Engineer", ["Frontend Engineer"]) < 85


def test_score_title_without_preferences_is_neutral():
    assert score_title("Software Engineer", []) == 60
    assert score_title("Software Engineer", None) == 60


# --------------------------------------------------------------------------- scoring: experience


@pytest.mark.parametrize(
    "job_min,job_max,years,expected",
    [
        (2, 5, 3, (100, "STRONG")),
        (2, 5, 2, (100, "STRONG")),
        (2, 5, 5, (100, "STRONG")),
        (3, 6, 2.5, (75, "GOOD")),  # within 1 year under
        (5, 8, 3, (30, "UNDER")),  # 2 years under -> 40 - 10
        (8, 10, 1, (10, "UNDER")),  # far under, floored at 10
        (2, 4, 6, (80, "GOOD")),  # at most 2 years over
        (2, 4, 9, (60, "OVER")),
        (None, None, 3, (60, "UNKNOWN")),
        (2, 5, None, (60, "UNKNOWN")),
    ],
)
def test_score_experience(job_min, job_max, years, expected):
    assert score_experience(job_min, job_max, years) == expected


def test_score_experience_handles_open_ended_ranges():
    assert score_experience(3, None, 4) == (100, "STRONG")
    assert score_experience(None, 4, 2) == (100, "STRONG")


# --------------------------------------------------------------------------- scoring: location


def test_score_location_labels():
    assert score_location("Remote", WorkMode.REMOTE, ["Bangalore", "Remote"], []) == (100, "REMOTE_OK")
    assert score_location("Bengaluru", WorkMode.HYBRID, ["Bangalore"], []) == (100, "MATCH")
    assert score_location("Chennai", WorkMode.ONSITE, ["Bangalore", "Remote"], []) == (20, "MISMATCH")
    assert score_location("Chennai", WorkMode.ONSITE, [], []) == (60, "UNKNOWN")
    assert score_location(None, None, ["Bangalore"], []) == (60, "UNKNOWN")


def test_score_location_remote_without_a_remote_preference():
    score, label = score_location("Remote", WorkMode.REMOTE, ["Bangalore"], [])
    assert label == "REMOTE_OK" and 60 <= score < 100


def test_score_location_accepts_remote_via_work_modes():
    assert score_location("Remote", WorkMode.REMOTE, [], [WorkMode.REMOTE]) == (100, "REMOTE_OK")


# --------------------------------------------------------------------------- scoring: salary


def test_score_salary_labels():
    assert score_salary(1500000, 2500000, 1200000, 2000000) == (100, "ABOVE")
    assert score_salary(1200000, 1800000, 1200000, 2000000) == (75, "WITHIN")
    assert score_salary(600000, 900000, 1200000, 2000000) == (20, "BELOW")
    assert score_salary(None, None, 1200000, 2000000) == (None, "UNKNOWN")
    assert score_salary(1500000, 2500000, None, None) == (None, "UNKNOWN")


# --------------------------------------------------------------------------- scoring: preferences


def test_score_preferences_rewards_matching_work_mode_and_tech():
    score, details = scoring.score_preferences(
        work_mode=WorkMode.REMOTE,
        employment_type=EmploymentType.FULL_TIME,
        job_skills=["React", "Node.js"],
        preferred_work_modes=[WorkMode.REMOTE],
        preferred_employment_types=[EmploymentType.FULL_TIME],
        preferred_technologies=["React", "Node.js"],
    )
    assert score == 100
    assert details["work_mode"] is True


def test_score_preferences_penalises_excluded_keywords():
    score, details = scoring.score_preferences(
        work_mode=WorkMode.ONSITE,
        employment_type=EmploymentType.FULL_TIME,
        job_skills=["PHP"],
        preferred_work_modes=[WorkMode.REMOTE],
        preferred_employment_types=[],
        preferred_technologies=[],
        excluded_keywords=["night shift"],
        text="This role requires a night shift rotation.",
    )
    assert score <= 10
    assert details["excluded_keywords"] == ["night shift"]


def test_score_preferences_is_neutral_without_preferences():
    score, _ = scoring.score_preferences(
        work_mode=None,
        employment_type=None,
        job_skills=[],
        preferred_work_modes=[],
        preferred_employment_types=[],
        preferred_technologies=[],
    )
    assert score == 60


# --------------------------------------------------------------------------- scoring: combine


def test_combine_applies_the_contract_weights():
    result = combine(skills=100, title=100, experience=100, location=100, salary=100, preference=100)
    assert result["score"] == 100  # 100 + P2 bonus, clamped
    assert result["base_score"] == 100.0
    assert sum(result["weights"].values()) == pytest.approx(1.0)
    assert result["weights"]["skills"] == pytest.approx(0.40)
    assert result["weights"]["salary"] == pytest.approx(0.10)


def test_combine_weighted_average_is_correct():
    result = combine(
        skills=80, title=60, experience=100, location=50, salary=20, preference=60, priority=CompanyPriority.P3
    )
    expected = 0.40 * 80 + 0.15 * 60 + 0.20 * 100 + 0.10 * 50 + 0.10 * 20 + 0.05 * 60
    assert result["base_score"] == pytest.approx(expected, abs=0.01)
    assert result["score"] == round(expected)


def test_combine_redistributes_the_salary_weight_when_unknown():
    with_salary = combine(skills=80, title=80, experience=80, location=80, salary=80, preference=80)
    without_salary = combine(skills=80, title=80, experience=80, location=80, salary=None, preference=80)
    assert without_salary["base_score"] == pytest.approx(with_salary["base_score"])
    assert "salary" not in without_salary["weights"]
    assert without_salary["redistributed"] == ["salary"]
    assert sum(without_salary["weights"].values()) == pytest.approx(1.0)
    # the remaining weights keep their relative proportions
    assert without_salary["weights"]["skills"] == pytest.approx(0.40 / 0.90, abs=1e-4)


def test_combine_redistribution_changes_the_score_when_parts_differ():
    low_salary = combine(skills=90, title=90, experience=90, location=90, salary=0, preference=90)
    unknown_salary = combine(skills=90, title=90, experience=90, location=90, salary=None, preference=90)
    assert unknown_salary["score"] > low_salary["score"]


def test_combine_priority_adjustment_is_capped():
    base = combine(skills=50, title=50, experience=50, location=50, salary=50, preference=50, priority=CompanyPriority.P3)
    p1 = combine(skills=50, title=50, experience=50, location=50, salary=50, preference=50, priority=CompanyPriority.P1)
    p2 = combine(skills=50, title=50, experience=50, location=50, salary=50, preference=50, priority=CompanyPriority.P2)
    assert base["score"] == 50 and base["priority_adjustment"] == 0
    assert p1["score"] == 55 and p1["priority_adjustment"] == 5
    assert p2["score"] == 52 and p2["priority_adjustment"] == 2


def test_combine_avoid_forces_zero():
    result = combine(skills=100, title=100, experience=100, location=100, salary=100, preference=100, priority=CompanyPriority.AVOID)
    assert result["score"] == 0
    assert result["priority_adjustment"] == 0
    assert result["priority"] == "AVOID"


def test_combine_clamps_and_tolerates_bad_input():
    assert combine(skills=250, title=-40, experience=50, location=50)["parts"]["skills"] == 100
    assert combine(skills=250, title=-40, experience=50, location=50)["parts"]["title"] == 0
    assert combine(skills=50, title=50, experience=50, location=50, priority="nonsense")["priority"] == "P2"
    assert combine(skills=50, title=50, experience=50, location=50)["redistributed"] == ["preference", "salary"]


# --------------------------------------------------------------------------- persistence


@pytest.fixture
def user(db) -> User:
    row = User(
        email="match-tester@example.com",
        hashed_password=hash_password("StrongPass123!"),
        full_name="Match Tester",
    )
    db.add(row)
    db.flush()
    db.add(
        UserProfile(
            user_id=row.id,
            skills=["React", "Node.js", "TypeScript"],
            technologies=["PostgreSQL"],
            years_of_experience=3.0,
        )
    )
    db.add(
        JobPreference(
            user_id=row.id,
            desired_titles=["Backend Engineer"],
            preferred_locations=["Bangalore", "Remote"],
            min_salary=1200000,
            desired_salary=2000000,
            min_match_score=75,
        )
    )
    db.commit()
    return row


@pytest.fixture
def api(client, user):
    token = create_access_token(user.id, user.role.value)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def make_job(db, *, title="Backend Engineer", company="Razorpay", location="Bangalore", **kwargs) -> Job:
    normalized = company.lower().replace(" ", "")
    row = db.scalars(select(Company).where(Company.normalized_name == normalized)).first()
    if row is None:
        row = Company(name=company, normalized_name=normalized)
        db.add(row)
        db.flush()
    job = Job(
        company_id=row.id,
        title=title,
        normalized_title=title.lower(),
        description=kwargs.pop("description", "Build APIs with Node.js and PostgreSQL."),
        location=location,
        normalized_location=(location or "").lower() or None,
        work_mode=kwargs.pop("work_mode", WorkMode.HYBRID),
        employment_type=EmploymentType.FULL_TIME,
        salary_min=kwargs.pop("salary_min", 1500000),
        salary_max=kwargs.pop("salary_max", 2500000),
        salary_currency="INR",
        experience_min=kwargs.pop("experience_min", 2.0),
        experience_max=kwargs.pop("experience_max", 5.0),
        required_skills=kwargs.pop("required_skills", ["Node.js", "PostgreSQL", "Kubernetes"]),
        preferred_skills=kwargs.pop("preferred_skills", ["Docker"]),
        posted_at=kwargs.pop("posted_at", datetime.now(timezone.utc) - timedelta(hours=5)),
        dedupe_hash=compute_dedupe_hash(normalized, title.lower(), (location or "").lower()),
        **kwargs,
    )
    db.add(job)
    db.flush()
    return job


def test_analyze_job_persists_every_part(db, user):
    job = make_job(db)
    match = service.analyze_job(db, user.id, job)
    db.commit()

    assert 0 <= match.match_score <= 100
    assert match.user_id == user.id and match.job_id == job.id
    assert match.experience_match == "STRONG"
    assert match.location_match == "MATCH"
    assert match.salary_match == "ABOVE"
    assert match.company_priority == CompanyPriority.P2
    assert match.missing_skills == ["Kubernetes"]
    assert match.skill_match["matched"] and match.skill_match["total"] == 3
    assert match.explanation
    assert match.details["weights"]
    assert match.analyzed_at is not None


def test_analyze_job_is_idempotent_upsert(db, user):
    job = make_job(db)
    first = service.analyze_job(db, user.id, job)
    db.commit()
    first_id, first_score = first.id, first.match_score

    second = service.analyze_job(db, user.id, job)
    db.commit()
    assert second.id == first_id
    assert second.match_score == first_score
    assert db.scalar(select(func.count(JobMatch.id))) == 1


def test_analyze_job_reflects_profile_changes(db, user):
    job = make_job(db)
    before = service.analyze_job(db, user.id, job).match_score
    db.commit()

    profile = db.scalars(select(UserProfile).where(UserProfile.user_id == user.id)).one()
    profile.skills = ["Node.js", "PostgreSQL", "Kubernetes"]
    db.commit()

    after = service.analyze_job(db, user.id, job).match_score
    db.commit()
    assert after > before
    assert db.scalar(select(func.count(JobMatch.id))) == 1


def test_analyze_job_honours_the_avoid_list(db, user):
    job = make_job(db, company="Wipro")
    db.add(
        CompanyPreference(
            user_id=user.id,
            company_id=job.company_id,
            company_name="Wipro",
            normalized_name=job.company.normalized_name,
            priority=CompanyPriority.AVOID,
        )
    )
    db.commit()

    match = service.analyze_job(db, user.id, job)
    db.commit()
    assert match.match_score == 0
    assert match.explanation == scoring.AVOID_EXPLANATION
    assert match.company_priority == CompanyPriority.AVOID


def test_analyze_job_adds_the_priority_bonus(db, user):
    job = make_job(db, company="Google")
    neutral = service.analyze_job(db, user.id, job).match_score
    db.commit()

    db.add(
        CompanyPreference(
            user_id=user.id,
            company_id=job.company_id,
            company_name="Google",
            normalized_name=job.company.normalized_name,
            priority=CompanyPriority.P1,
        )
    )
    db.commit()
    boosted = service.analyze_job(db, user.id, job).match_score
    db.commit()
    assert 0 < boosted - neutral <= 5


def test_analyze_job_writes_an_audit_entry(db, user):
    from app.models.audit import AuditLog

    job = make_job(db)
    service.analyze_job(db, user.id, job)
    db.commit()
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "job.analyzed")).one()
    assert entry.user_id == user.id
    assert entry.meta["job_id"] == str(job.id)
    assert "% match" in entry.message


def test_analyze_job_uses_resume_skills(db, user):
    job = make_job(db, required_skills=["Kubernetes", "Terraform"], preferred_skills=[])
    without = service.analyze_job(db, user.id, job).skill_score
    db.commit()

    db.add(
        Resume(
            user_id=user.id,
            name="Infra CV",
            is_default=True,
            file_path="/tmp/cv.pdf",
            original_filename="cv.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            parsed_data={"skills": ["Kubernetes", "Terraform"], "total_experience_years": 3.0},
        )
    )
    db.commit()
    with_resume = service.analyze_job(db, user.id, job).skill_score
    db.commit()
    assert with_resume == 100 > without


def test_analyze_jobs_scores_a_batch(db, user):
    jobs = [make_job(db, title=f"Backend Engineer {i}") for i in range(3)]
    db.commit()
    matches = service.analyze_jobs(db, user.id, jobs)
    db.commit()
    assert len(matches) == 3
    assert db.scalar(select(func.count(JobMatch.id))) == 3
    assert service.analyze_jobs(db, user.id, []) == []


def test_salary_weight_is_redistributed_for_jobs_without_salary(db, user):
    with_salary = make_job(db, title="Backend Engineer A")
    without_salary = make_job(db, title="Backend Engineer B", salary_min=None, salary_max=None)
    db.commit()

    a = service.analyze_job(db, user.id, with_salary)
    b = service.analyze_job(db, user.id, without_salary)
    db.commit()
    assert a.salary_score == 100 and a.salary_match == "ABOVE"
    assert b.salary_score is None and b.salary_match == "UNKNOWN"
    assert "salary" in b.details["redistributed"]
    assert "salary" not in b.details["weights"]


# --------------------------------------------------------------------------- API


def test_analyze_all_and_summary(api, db, user):
    make_job(db, title="Backend Engineer A")
    make_job(db, title="Backend Engineer B", company="Infosys", location="Chennai", salary_min=400000, salary_max=700000)
    db.commit()

    result = api.post(f"{API}/analyze-all").json()
    assert result["analyzed"] == 2
    assert 0 <= result["average_score"] <= 100
    assert result["high_match"] <= result["analyzed"]

    summary = api.get(f"{API}/summary").json()
    assert summary["total_jobs"] == 2
    assert summary["analyzed"] == 2
    assert summary["min_match_score"] == 75
    assert summary["queued"] == 0
    assert summary["matched_at_or_above_min"] >= summary["high_match"]


def test_analyze_all_only_unanalyzed(api, db, user):
    first = make_job(db, title="Backend Engineer A")
    db.commit()
    service.analyze_job(db, user.id, first)
    db.commit()

    make_job(db, title="Backend Engineer B")
    db.commit()

    result = api.post(f"{API}/analyze-all", json={"only_unanalyzed": True}).json()
    assert result["analyzed"] == 1
    db.expire_all()
    assert db.scalar(select(func.count(JobMatch.id))) == 2


def test_summary_counts_queued_applications(api, db, user):
    from app.models.application import Application

    job = make_job(db)
    db.commit()
    db.add(Application(user_id=user.id, job_id=job.id, status=ApplicationStatus.QUEUED))
    db.commit()
    assert api.get(f"{API}/summary").json()["queued"] == 1


def test_matching_endpoints_require_authentication(client):
    assert client.get(f"{API}/summary").status_code == 401
    assert client.post(f"{API}/analyze-all").status_code == 401


def test_analyze_all_rejects_another_users_resume(api, db, user):
    other = User(email="thief@example.com", hashed_password=hash_password("StrongPass123!"), full_name="Thief")
    db.add(other)
    db.flush()
    resume = Resume(
        user_id=other.id,
        name="Their CV",
        file_path="/tmp/other.pdf",
        original_filename="other.pdf",
        mime_type="application/pdf",
        size_bytes=10,
    )
    db.add(resume)
    db.commit()
    assert api.post(f"{API}/analyze-all", json={"resume_id": str(resume.id)}).status_code == 404


def test_job_scores_are_isolated_per_user(db, user):
    job = make_job(db)
    other = User(email="second@example.com", hashed_password=hash_password("StrongPass123!"), full_name="Second")
    db.add(other)
    db.flush()
    db.add(UserProfile(user_id=other.id, skills=["COBOL"], years_of_experience=15.0))
    db.add(JobPreference(user_id=other.id, desired_titles=["Mainframe Engineer"], preferred_locations=["Chennai"]))
    db.commit()

    mine = service.analyze_job(db, user.id, job)
    theirs = service.analyze_job(db, other.id, job)
    db.commit()
    assert mine.id != theirs.id
    assert mine.match_score > theirs.match_score
    assert db.scalar(select(func.count(JobMatch.id))) == 2
