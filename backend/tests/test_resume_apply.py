"""Apply resume suggestions: plan building, the apply rules and both endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.audit import AuditLog
from app.models.company import Company
from app.models.enums import EmploymentType, WorkMode
from app.models.job import Job
from app.models.profile import JobPreference, UserProfile
from app.models.resume import Resume, ResumeVersion
from app.models.user import User
from app.modules.jobs.dedupe import compute_dedupe_hash
from app.modules.matching import service as matching_service
from app.modules.resumes import apply as apply_mod
from app.modules.resumes import recommendations as rec_mod
from app.modules.resumes import service as resume_service
from app.modules.resumes.schemas import ApplicableChange, Recommendation, RecommendationEvidence

try:  # pytest puts ``tests/`` on sys.path; the package path is the fallback
    from helpers.documents import build_pdf
except ImportError:  # pragma: no cover
    from tests.helpers.documents import build_pdf  # type: ignore[no-redef]

RESUMES = "/api/v1/resumes"
WEAK_1 = "Worked on billing APIs in Python."
WEAK_2 = "Helped with postgres query tuning for reports."


@pytest.fixture(autouse=True)
def _fresh_cache():
    rec_mod.clear_cache()
    yield
    rec_mod.clear_cache()


def parsed_resume(**overrides) -> dict:
    base = {
        "name": "Asha Rao",
        "email": "asha@example.com",
        "phone": "+91 90000 00000",
        "summary": "Backend developer.",
        "skills": ["Python", "Docker", "AWS"],
        "experience": [
            {
                "company": "Northwind",
                "title": "Backend Engineer",
                "start": "2022-01",
                "end": "Present",
                "description": f"- {WEAK_1}\n- {WEAK_2}\n- Reduced cloud costs by 20%.",
                "technologies": ["Python", "Docker", "AWS"],
            }
        ],
        "education": [{"institution": "IIT", "degree": "B.Tech", "field": "CS", "start": "2016", "end": "2020"}],
        "projects": [],
        "certifications": [],
        "total_experience_years": 4.0,
        "links": {"linkedin": None, "github": None, "portfolio": None},
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- pure helpers


def _facts(parsed: dict | None = None, *, years: float | None = 4.0, titles=("Backend Engineer",), profile_skills=()):
    return apply_mod._Facts(
        parsed=parsed or parsed_resume(),
        raw_text="",
        inputs=rec_mod.MatchInputs(
            base_skills=list(profile_skills), profile_years=years, desired_titles=list(titles)
        ),
    )


def _resume_stub(version: int = 1):
    return SimpleNamespace(id=uuid.uuid4(), current_version=version)


def _rec(rec_id: str, category: str, **kw) -> Recommendation:
    kw.setdefault("priority", "HIGH")
    kw.setdefault("title", rec_id)
    kw.setdefault("detail", f"detail of {rec_id}")
    return Recommendation(id=rec_id, category=category, **kw)


def test_plan_kinds_and_default_selection():
    recs = [
        _rec("missing-skill-postgresql", "MISSING_SKILL", action="list", skills=["PostgreSQL"], estimated_score_gain=3.5),
        _rec("missing-skill-kubernetes", "MISSING_SKILL", action="add", skills=["Kubernetes"]),
        _rec("missing-skill-tensorflow", "MISSING_SKILL", action="learn", skills=["TensorFlow"]),
        _rec("weak-summary", "WEAK_SUMMARY", skills=["Python"]),
        _rec(
            "experience-bullets-northwind",
            "EXPERIENCE_BULLETS",
            suggested_text="Worked on billing APIs in Python, resulting in [X% fewer failed payments].",
            evidence=[
                RecommendationEvidence(label="Backend Engineer at Northwind", field="experience[0]"),
                RecommendationEvidence(label=WEAK_1, field="experience[0].bullet"),
                RecommendationEvidence(label=WEAK_2, field="experience[0].bullet"),
            ],
        ),
        _rec("keyword-gap", "KEYWORD_GAP", priority="LOW"),
        _rec("title-alignment", "TITLE_ALIGNMENT"),
        _rec("section-missing-links", "SECTION_MISSING"),
        _rec("format-too-short", "LENGTH_AND_FORMAT"),
        _rec("stale-content", "STALE_CONTENT", priority="LOW"),
    ]
    plan = apply_mod.plan_from(_resume_stub(3), recs, _facts())
    assert plan.resume_version == 3
    changes = {c.id: c for c in plan.changes}

    pg = changes["missing-skill-postgresql"]
    assert (pg.kind, pg.after, pg.target, pg.selected_by_default, pg.requires_confirmation) == (
        "ADD_SKILL", "PostgreSQL", "skills", True, False,
    )
    assert pg.estimated_score_gain == 3.5

    k8s = changes["missing-skill-kubernetes"]
    assert not k8s.selected_by_default and k8s.requires_confirmation
    assert k8s.confirmation_label == "I have used Kubernetes"

    summary = changes["weak-summary"]
    assert summary.kind == "REPLACE_SUMMARY" and summary.selected_by_default
    assert summary.before == "Backend developer."
    assert not apply_mod.has_placeholder(summary.after)

    b1 = changes["experience-bullets-northwind--bullet-1"]
    b2 = changes["experience-bullets-northwind--bullet-2"]
    assert b1.kind == b2.kind == "REPLACE_BULLET"
    assert b1.target == "experience[0].description"
    assert (b1.before, b2.before) == (WEAK_1, WEAK_2)
    # A ticked bullet applies as finished text: the placeholder suggestion is rejected and the
    # deterministic polish (mock provider) supplies a stronger opening verb, nothing invented.
    assert b1.after == "Developed billing APIs in Python."
    assert b2.after == "Contributed to postgres query tuning for reports."
    assert not b1.has_placeholders and not b2.has_placeholders
    assert b1.selected_by_default and b2.selected_by_default
    assert not b1.requires_confirmation and not b2.requires_confirmation

    assert {m.recommendation_id for m in plan.manual} == {
        "missing-skill-tensorflow", "keyword-gap", "title-alignment", "section-missing-links",
        "format-too-short", "stale-content",
    }
    assert next(m for m in plan.manual if m.recommendation_id == "keyword-gap").detail == "detail of keyword-gap"


def test_clean_llm_summary_is_used_and_one_with_invented_facts_is_not():
    clean = "Backend Engineer working with Python, Docker and AWS on billing APIs."
    plan = apply_mod.plan_from(_resume_stub(), [_rec("weak-summary", "WEAK_SUMMARY", suggested_text=clean)], _facts())
    assert plan.changes[0].after == clean

    for invented in (
        "Backend Engineer with 9 years of experience in Python.",  # number not on the resume
        "Backend Engineer working with Python and Kubernetes.",  # skill not on the resume
        "Backend Engineer who delivered [the outcome you are proudest of].",  # placeholder
    ):
        plan = apply_mod.plan_from(
            _resume_stub(), [_rec("weak-summary", "WEAK_SUMMARY", suggested_text=invented)], _facts()
        )
        after = plan.changes[0].after
        assert after != invented
        assert after == apply_mod.build_factual_summary(_facts())


def test_factual_summary_uses_only_resume_and_profile_facts():
    text = apply_mod.build_factual_summary(_facts(titles=("Platform Engineer",)), ["AWS"])
    assert text == (
        "Backend Engineer with 4 years of experience working with AWS, Python and Docker. "
        "Currently Backend Engineer at Northwind. Seeking Platform Engineer roles."
    )
    assert apply_mod.summary_problem(text, _facts(titles=("Platform Engineer",)), check_skills=True) is None
    # no years anywhere: no number is written
    no_years = parsed_resume(total_experience_years=None)
    assert "years" not in apply_mod.build_factual_summary(_facts(no_years, years=None))
    # nothing to build from
    assert apply_mod.build_factual_summary(_facts(parsed_resume(skills=[], experience=[]), titles=())) is None


def test_summary_fact_check_rejects_invented_numbers_but_allows_profile_years():
    facts = _facts(parsed_resume(total_experience_years=None), years=6.0)
    assert apply_mod.summary_problem("Engineer with 6 years of experience.", facts, check_skills=False) is None
    assert apply_mod.summary_problem("Engineer with 7 years of experience.", facts, check_skills=False) == "invented_number"
    assert apply_mod.summary_problem("Cut costs by 20%.", facts, check_skills=False) is None  # 20 is on the resume


def test_skills_are_canonicalised_and_deduplicated():
    parsed = parsed_resume(skills=["python3", "postgres"])
    changes = [
        ApplicableChange(id="a", recommendation_id="a", kind="ADD_SKILL", title="a", after="PostgreSQL", target="skills"),
        ApplicableChange(id="b", recommendation_id="b", kind="ADD_SKILL", title="b", after="kubernetes", target="skills"),
        ApplicableChange(id="c", recommendation_id="c", kind="ADD_SKILL", title="c", after="k8s", target="skills"),
    ]
    data, applied, skipped = apply_mod.apply_to_parsed(parsed, changes)
    assert data["skills"] == ["python3", "postgres", "Kubernetes"]
    assert [c.id for c in applied] == ["b"]
    assert {(s.id, s.reason) for s in skipped} == {("a", "already_listed"), ("c", "already_listed")}
    assert parsed["skills"] == ["python3", "postgres"]  # the input is never mutated


def test_bullet_is_replaced_exactly_once_and_skipped_when_not_found():
    description = f"- {WEAK_1}\n- {WEAK_2}\n- {WEAK_1}"
    parsed = parsed_resume()
    parsed["experience"][0]["description"] = description
    change = ApplicableChange(
        id="x--bullet-1", recommendation_id="x", kind="REPLACE_BULLET", title="t", before=WEAK_1,
        after="Built billing APIs in Python for 3 teams.", target="experience[0].description",
    )
    gone = change.model_copy(update={"id": "x--bullet-2", "before": "A bullet that is not there."})
    data, applied, skipped = apply_mod.apply_to_parsed(parsed, [change, gone])
    new = data["experience"][0]["description"]
    assert new.count("Built billing APIs in Python for 3 teams.") == 1
    assert new.startswith("- Built billing APIs in Python for 3 teams.\n")
    assert [c.id for c in applied] == ["x--bullet-1"]
    assert [(s.id, s.reason) for s in skipped] == [("x--bullet-2", "bullet_not_found")]


def test_invalidate_resume_drops_only_that_resumes_entries():
    rid, other = uuid.uuid4(), uuid.uuid4()
    value = object()
    rec_mod._CACHE[(str(rid), "t1", "f")] = (rec_mod._clock() + 60, value)  # type: ignore[assignment]
    rec_mod._CACHE[(str(rid), "t2", "g")] = (rec_mod._clock() + 60, value)  # type: ignore[assignment]
    rec_mod._CACHE[(str(other), "t1", "f")] = (rec_mod._clock() + 60, value)  # type: ignore[assignment]
    assert rec_mod.invalidate_resume(rid) == 2
    assert list(rec_mod._CACHE) == [(str(other), "t1", "f")]


# --------------------------------------------------------------------------- API


def _user(db: Session, email: str) -> User:
    user = User(email=email, hashed_password=hash_password("StrongPass123!"), full_name="Asha Rao", is_active=True)
    db.add(user)
    db.flush()
    return user


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}


def _job(db: Session, company: str, required: list[str]) -> Job:
    normalized = company.lower()
    row = Company(name=company, normalized_name=normalized)
    db.add(row)
    db.flush()
    job = Job(
        company_id=row.id,
        title="Backend Engineer",
        normalized_title="backend engineer",
        description="Own payments services end to end.",
        location="Bangalore",
        normalized_location="bangalore",
        work_mode=WorkMode.HYBRID,
        employment_type=EmploymentType.FULL_TIME,
        experience_min=1.0,
        experience_max=6.0,
        required_skills=required,
        preferred_skills=[],
        posted_at=datetime.now(timezone.utc),
        dedupe_hash=compute_dedupe_hash(normalized, "backend engineer", "bangalore"),
    )
    db.add(job)
    db.flush()
    return job


@pytest.fixture
def seeded(db: Session):
    owner = _user(db, "asha@example.com")
    db.add(UserProfile(user_id=owner.id, years_of_experience=4.0))
    db.add(JobPreference(user_id=owner.id, desired_titles=["Backend Engineer"], preferred_locations=["Bangalore"]))
    db.flush()
    resume = resume_service.create_resume_from_bytes(db, owner.id, "asha.pdf", build_pdf())
    resume.parsed_data = parsed_resume()
    resume.text_content = None
    db.add(resume)
    jobs = [_job(db, f"Co{i}", ["PostgreSQL", "Kubernetes", "TensorFlow"]) for i in range(3)]
    matching_service.analyze_jobs(db, owner.id, jobs)
    other = _user(db, "other@example.com")
    db.commit()
    return {"owner": owner, "other": other, "resume_id": str(resume.id)}


def _plan(client: TestClient, resume_id: str) -> dict:
    response = client.get(f"{RESUMES}/{resume_id}/recommendations/apply-plan")
    assert response.status_code == 200, response.text
    return response.json()


def test_apply_plan_endpoint(client: TestClient, seeded):
    client.headers.update(_headers(seeded["owner"]))
    plan = _plan(client, seeded["resume_id"])
    assert plan["resume_id"] == seeded["resume_id"] and plan["resume_version"] == 1
    changes = {c["id"]: c for c in plan["changes"]}
    assert changes["missing-skill-postgresql"]["selected_by_default"] is True
    assert changes["missing-skill-kubernetes"]["requires_confirmation"] is True
    assert changes["weak-summary"]["kind"] == "REPLACE_SUMMARY"
    assert "[" not in changes["weak-summary"]["after"]
    bullet = changes["experience-bullets-northwind--bullet-1"]
    assert bullet["has_placeholders"] is False and "[" not in bullet["after"]
    assert bullet["selected_by_default"] is True and bullet["requires_confirmation"] is False
    assert "missing-skill-tensorflow" not in changes
    assert "missing-skill-tensorflow" in {m["recommendation_id"] for m in plan["manual"]}


def test_apply_saves_a_new_version_and_returns_fresh_recommendations(client: TestClient, seeded, db: Session):
    client.headers.update(_headers(seeded["owner"]))
    base = f"{RESUMES}/{seeded['resume_id']}"
    before = client.get(f"{base}/recommendations").json()  # warms the cache
    assert "missing-skill-postgresql" in {r["id"] for r in before["recommendations"]}

    typed = "Built billing APIs in Python used by 3 product teams."
    response = client.post(
        f"{base}/recommendations/apply",
        json={
            "resume_version": 1,
            "changes": [
                {"id": "missing-skill-postgresql"},
                {"id": "weak-summary"},
                {"id": "experience-bullets-northwind--bullet-1", "after": typed},  # user's own claim: numbers allowed
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [a["id"] for a in body["applied"]] == [
        "missing-skill-postgresql", "weak-summary", "experience-bullets-northwind--bullet-1",
    ]
    assert body["skipped"] == []
    resume = body["resume"]
    assert resume["current_version"] == 2
    assert resume["parsed_data"]["skills"] == ["Python", "Docker", "AWS", "PostgreSQL"]
    assert resume["parsed_data"]["summary"] != "Backend developer."
    description = resume["parsed_data"]["experience"][0]["description"]
    assert description.count(typed) == 1 and WEAK_1 not in description and WEAK_2 in description

    recs = body["recommendations"]
    assert recs["resume_version"] == 2 and recs["cached"] is False
    assert "missing-skill-postgresql" not in {r["id"] for r in recs["recommendations"]}
    assert [v["version_number"] for v in recs["version_history"]] == [1, 2]
    assert recs["version_history"][-1]["note"] == "Applied 3 suggestions"

    version = db.scalars(
        select(ResumeVersion).where(ResumeVersion.resume_id == uuid.UUID(seeded["resume_id"]), ResumeVersion.version_number == 2)
    ).one()
    assert version.note == "Applied 3 suggestions"
    assert version.parsed_data["skills"][-1] == "PostgreSQL"
    log = db.scalars(select(AuditLog).where(AuditLog.action == "resume.suggestions_applied")).one()
    assert log.meta["applied"] == [a["id"] for a in body["applied"]]

    # the stale v1 entries are gone; the fresh result is what the next GET serves
    db.expire_all()
    current_key = db.get(Resume, uuid.UUID(seeded["resume_id"])).updated_at.isoformat()
    assert [key[1] for key in rec_mod._CACHE if key[0] == seeded["resume_id"]] == [current_key]
    again = client.get(f"{base}/recommendations").json()
    assert again["cached"] is True and again["resume_version"] == 2


def test_placeholder_left_is_rejected(client: TestClient, seeded):
    client.headers.update(_headers(seeded["owner"]))
    base = f"{RESUMES}/{seeded['resume_id']}"
    for change in (
        {"id": "experience-bullets-northwind--bullet-2", "after": "Tuned queries, saving [N hours]."},
        {"id": "weak-summary", "after": "Backend Engineer delivering [outcome]."},
    ):
        response = client.post(f"{base}/recommendations/apply", json={"resume_version": 1, "changes": [change]})
        assert response.status_code == 422, response.text
        error = response.json()["error"]
        assert error["code"] == "placeholder_left" and error["details"]["id"] == change["id"]
    assert client.get(base).json()["current_version"] == 1


def test_summary_with_an_invented_number_is_rejected(client: TestClient, seeded):
    client.headers.update(_headers(seeded["owner"]))
    response = client.post(
        f"{RESUMES}/{seeded['resume_id']}/recommendations/apply",
        json={"resume_version": 1, "changes": [{"id": "weak-summary", "after": "Backend Engineer with 9 years of Python."}]},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invented_number" and error["details"] == {"id": "weak-summary", "numbers": ["9"]}

    ok = client.post(
        f"{RESUMES}/{seeded['resume_id']}/recommendations/apply",
        json={"resume_version": 1, "changes": [{"id": "weak-summary", "after": "Backend Engineer with 4 years of Python."}]},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["resume"]["parsed_data"]["summary"] == "Backend Engineer with 4 years of Python."


def test_unknown_change_and_smuggled_skills_are_refused(client: TestClient, seeded):
    client.headers.update(_headers(seeded["owner"]))
    url = f"{RESUMES}/{seeded['resume_id']}/recommendations/apply"
    for change in ({"id": "missing-skill-rust"}, {"id": "missing-skill-tensorflow"}):  # not in plan / learn-only
        response = client.post(url, json={"resume_version": 1, "changes": [change]})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "unknown_change"

    # the client's text, kind and target are ignored for a skill: only the plan's skill is added
    response = client.post(
        url,
        json={
            "resume_version": 1,
            "changes": [{"id": "missing-skill-postgresql", "after": "Rust", "kind": "ADD_SKILL", "target": "summary"}],
        },
    )
    assert response.status_code == 200, response.text
    parsed = response.json()["resume"]["parsed_data"]
    assert parsed["skills"] == ["Python", "Docker", "AWS", "PostgreSQL"]
    assert parsed["summary"] == "Backend developer."


def test_stale_plan_is_a_conflict(client: TestClient, seeded):
    client.headers.update(_headers(seeded["owner"]))
    base = f"{RESUMES}/{seeded['resume_id']}"
    parsed = client.get(base).json()["parsed_data"]
    assert client.put(f"{base}/parsed-data", json=parsed).status_code == 200  # another tab saved v2
    response = client.post(
        f"{base}/recommendations/apply", json={"resume_version": 1, "changes": [{"id": "missing-skill-postgresql"}]}
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "stale_plan" and error["details"]["current_version"] == 2
    assert _plan(client, seeded["resume_id"])["resume_version"] == 2


def test_another_users_resume_is_not_found(client: TestClient, seeded):
    client.headers.update(_headers(seeded["other"]))
    base = f"{RESUMES}/{seeded['resume_id']}/recommendations"
    assert client.get(f"{base}/apply-plan").status_code == 404
    response = client.post(f"{base}/apply", json={"resume_version": 1, "changes": [{"id": "missing-skill-postgresql"}]})
    assert response.status_code == 404


def test_endpoints_require_authentication_and_a_valid_body(client: TestClient, seeded):
    base = f"{RESUMES}/{seeded['resume_id']}/recommendations"
    assert client.get(f"{base}/apply-plan").status_code == 401
    client.headers.update(_headers(seeded["owner"]))
    assert client.post(f"{base}/apply", json={"resume_version": 1, "changes": []}).status_code == 422


def test_bullet_without_a_safe_improvement_is_not_offered():
    """A bullet that already opens strongly gets no change rather than a made-up outcome."""
    strong = "Built billing APIs in Python."
    parsed = {"experience": [{"title": "Backend Engineer", "company": "Northwind", "description": f"- {strong}"}]}
    rec = _rec(
        "experience-bullets-northwind",
        "EXPERIENCE_BULLETS",
        suggested_text="Built billing APIs in Python, resulting in [X% fewer failed payments].",
        evidence=[
            RecommendationEvidence(label="Backend Engineer at Northwind", field="experience[0]"),
            RecommendationEvidence(label=strong, field="experience[0].bullet"),
        ],
    )
    plan = apply_mod.plan_from(_resume_stub(1), [rec], _facts(parsed))
    assert plan.changes == []


def test_generated_bullet_with_invented_facts_falls_back_to_the_polish(monkeypatch):
    facts = _facts()
    original = "Worked on billing APIs in Python."
    assert apply_mod.bullet_problem("Developed billing APIs in Python, cutting failures by 40%.", original, facts) == "invented_number"
    assert apply_mod.bullet_problem("Developed billing APIs in Python and Kubernetes.", original, facts) == "invented_skill"
    assert apply_mod.bullet_problem("Developed billing APIs in Python, improving payment reliability.", original, facts) is None

    monkeypatch.setattr(apply_mod, "_llm_bullet", lambda bullet, entry: "Developed billing APIs in Python, cutting failures by 40%.")
    apply_mod._BULLET_CACHE.clear()
    assert apply_mod.strengthen_bullet(original, {}, facts) == "Developed billing APIs in Python."

    monkeypatch.setattr(apply_mod, "_llm_bullet", lambda bullet, entry: "Developed billing APIs in Python for the payments team.")
    apply_mod._BULLET_CACHE.clear()
    assert apply_mod.strengthen_bullet(original, {}, facts) == "Developed billing APIs in Python for the payments team."


def test_tidy_bullet_replaces_weak_openers():
    assert apply_mod.tidy_bullet("responsible for the release pipeline") == "Owned release pipeline."
    assert apply_mod.tidy_bullet("- helped with onboarding docs.") == "Contributed to onboarding docs."
    assert apply_mod.tidy_bullet("Designed the schema") == "Designed the schema."



def test_advice_text_is_never_used_as_resume_content():
    facts = _facts()
    advice = "Add a sentence to your summary highlighting your expertise in Kubernetes."
    assert apply_mod.looks_like_advice(advice)
    assert apply_mod.looks_like_advice("Consider listing Docker earlier.")
    assert not apply_mod.looks_like_advice("Backend Engineer with 4 years of experience in Python.")
    assert apply_mod.summary_problem(advice, facts, check_skills=False) == "advice_text"
    assert apply_mod.bullet_problem("Strengthen your bullets by adding numbers.", "Worked on billing APIs in Python.", facts) == "advice_text"

    rec = _rec("weak-summary", "WEAK_SUMMARY", skills=["Python"], suggested_text=advice)
    plan = apply_mod.plan_from(_resume_stub(1), [rec], facts)
    summary = next(c for c in plan.changes if c.kind == "REPLACE_SUMMARY")
    assert summary.after != advice and not apply_mod.looks_like_advice(summary.after)


def test_full_summary_is_never_replaced_and_pasted_bullets_are_not_a_summary():
    parsed = {
        "summary": " ".join(["Full stack developer building React and Node.js products on AWS"] * 3),
        "skills": ["React", "Node.js"],
        "experience": [{"title": "Engineer", "company": "Acme", "description": "- Built a React dashboard used by many internal users."}],
    }
    facts = _facts(parsed)
    rec = _rec("weak-summary", "WEAK_SUMMARY", skills=["React"], suggested_text="Built a React dashboard used by many internal users.")
    assert [c for c in apply_mod.plan_from(_resume_stub(1), [rec], facts).changes if c.kind == "REPLACE_SUMMARY"] == []

    thin = dict(parsed, summary="Developer.")
    assert apply_mod.summary_problem("Built a React dashboard used by many internal users.", _facts(thin), check_skills=False) == "copied_bullets"



def test_generic_result_clauses_are_stripped_but_real_content_is_kept():
    s = apply_mod.strip_filler
    assert s("Built analytics models that turn raw data into insights for better business outcomes.",
             "Built analytics models that turn raw data into insights.") == "Built analytics models that turn raw data into insights."
    assert s("Developed React frontends with Node.js backends to deliver robust enterprise applications.",
             "Developed React frontends with Node.js backends.") == "Developed React frontends with Node.js backends."
    assert s("Deployed solutions using Docker and AWS, ensuring robust system performance.",
             "Deployed solutions using Docker and AWS.") == "Deployed solutions using Docker and AWS."
    # the bullet's own clause is content, not filler
    kept = "Deployed services with Docker for scalability and reliability."
    assert s(kept, kept) == kept
    # a specific addition stays
    assert s("Developed billing APIs in Python for the payments team.", "Worked on billing APIs in Python.") == (
        "Developed billing APIs in Python for the payments team."
    )


def test_a_rewrite_that_is_only_filler_is_not_offered(monkeypatch):
    facts = _facts()
    original = "Built billing APIs in Python."
    monkeypatch.setattr(apply_mod, "_llm_bullet", lambda bullet, entry: "Built billing APIs in Python, enhancing operational efficiency.")
    apply_mod._BULLET_CACHE.clear()
    # filler stripped -> identical to the original -> the deterministic polish (also identical) -> no change
    assert apply_mod.strengthen_bullet(original, {}, facts).rstrip(".") == original.rstrip(".")
