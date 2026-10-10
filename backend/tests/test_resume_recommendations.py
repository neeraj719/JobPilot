"""Resume improvement recommendations (Step 4): rules, score maths, cache, AI polish, API."""
from __future__ import annotations

import copy
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.company import Company
from app.models.enums import EmploymentType, WorkMode
from app.models.job import Job
from app.models.profile import JobPreference, UserProfile
from app.models.user import User
from app.modules.ai import tasks as ai_tasks
from app.modules.ai.providers.mock import MockLLMProvider
from app.modules.jobs.dedupe import compute_dedupe_hash
from app.modules.matching import scoring
from app.modules.matching import service as matching_service
from app.modules.resumes import recommendations as rec
from app.modules.resumes import service as resume_service
from app.modules.resumes.schemas import Recommendation

try:  # pytest puts ``tests/`` on sys.path; the package path is the fallback
    from helpers.documents import build_pdf
except ImportError:  # pragma: no cover
    from tests.helpers.documents import build_pdf  # type: ignore[no-redef]

TODAY = date(2026, 10, 4)
RESUMES = "/api/v1/resumes"


@pytest.fixture(autouse=True)
def _fresh_cache():
    rec.clear_cache()
    yield
    rec.clear_cache()


# --------------------------------------------------------------------------- builders


def parsed_resume(**overrides) -> dict:
    """A healthy backend resume; tests break one thing at a time."""
    base = {
        "name": "Asha Rao",
        "email": "asha@example.com",
        "phone": "+91 90000 00000",
        "summary": (
            "Backend Engineer with 4 years of experience building Python and PostgreSQL services on AWS. "
            "I own APIs end to end, from schema design and Docker packaging to on-call, and I care about "
            "reliable systems that stay fast as traffic grows."
        ),
        "skills": ["Python", "PostgreSQL", "Docker", "AWS", "FastAPI", "Redis"],
        "experience": [
            {
                "company": "Northwind",
                "title": "Backend Engineer",
                "start": "2022-01",
                "end": "Present",
                "description": (
                    "- Built FastAPI services handling 2M requests a day.\n"
                    "- Reduced p95 latency by 40% with Redis caching.\n"
                    "- Cut deploy time from 30 to 8 minutes with Docker."
                ),
                "technologies": ["Python", "FastAPI", "Redis", "Docker"],
            },
            {
                "company": "Acme",
                "title": "Software Engineer",
                "start": "2020-06",
                "end": "2021-12",
                "description": "- Increased test coverage from 40% to 85%.\n- Migrated 12 cron jobs to AWS Lambda.",
                "technologies": ["Python", "AWS"],
            },
        ],
        "education": [{"institution": "IIT", "degree": "B.Tech", "field": "CS", "start": "2016", "end": "2020"}],
        "projects": [{"name": "Ledger", "description": "Double-entry ledger API.", "technologies": ["Python"]}],
        "certifications": [],
        "total_experience_years": 4.0,
        "links": {"linkedin": "https://linkedin.com/in/asha", "github": "https://github.com/asha", "portfolio": None},
    }
    base.update(overrides)
    return base


def target(i: int, title: str = "Backend Engineer", required=("Python", "PostgreSQL"), **kw) -> rec.TargetJob:
    defaults = {
        "company": f"Company{i}",
        "description": "Build reliable services.",
        "location": "Bangalore",
        "experience_min": 2.0,
        "experience_max": 6.0,
    }
    defaults.update(kw)
    return rec.TargetJob(id=f"job-{i}", title=title, required_skills=tuple(required), **defaults)


INPUTS = rec.MatchInputs(desired_titles=["Backend Engineer"], preferred_locations=["Bangalore"])


#: Stands in for the extracted document text so the length rule sees a normal-sized resume.
FILLER_TEXT = "lorem " * 400


def analyze(parsed: dict, jobs: list[rec.TargetJob], inputs: rec.MatchInputs = INPUTS, **kw) -> rec.Analysis:
    kw.setdefault("raw_text", FILLER_TEXT)
    return rec.analyze_resume(parsed, jobs, inputs, today=TODAY, **kw)


def by_category(analysis: rec.Analysis, category: str) -> list[Recommendation]:
    return [r for r in analysis.recommendations if r.category == category]


def ids(analysis: rec.Analysis) -> set[str]:
    return {r.id for r in analysis.recommendations}


# --------------------------------------------------------------------------- baseline


def test_a_healthy_resume_gets_no_advice_and_full_marks():
    analysis = analyze(parsed_resume(), [target(i) for i in range(4)])
    assert analysis.recommendations == []
    assert analysis.overall_score == 100
    assert analysis.target_summary.jobs_analysed == 4
    assert analysis.target_summary.top_titles[0].title == "Backend Engineer"
    assert [s.skill for s in analysis.target_summary.top_skills] == ["Python", "PostgreSQL"]


# --------------------------------------------------------------------------- MISSING_SKILL


def test_missing_skill_needs_thirty_percent_of_target_jobs():
    jobs = [target(0, required=("Python", "Kafka"))] + [target(i) for i in range(1, 4)]  # Kafka: 1 of 4 = 25 %
    assert not by_category(analyze(parsed_resume(), jobs), "MISSING_SKILL")


@pytest.mark.parametrize(
    ("with_skill", "total", "priority"),
    [(3, 6, "HIGH"), (2, 5, "MEDIUM"), (3, 10, "LOW")],  # 50 %, 40 %, 30 %
)
def test_missing_skill_priority_follows_frequency(with_skill, total, priority):
    jobs = [target(i, required=("Python", "Kubernetes")) for i in range(with_skill)]
    jobs += [target(i) for i in range(with_skill, total)]
    [missing] = by_category(analyze(parsed_resume(), jobs), "MISSING_SKILL")
    assert missing.id == "missing-skill-kubernetes"
    assert missing.priority == priority
    assert missing.skills == ["Kubernetes"]
    assert {e.job_id for e in missing.evidence if e.job_id} == {f"job-{i}" for i in range(with_skill)}


def test_missing_skill_is_add_when_experience_shows_a_related_family_skill():
    # Kubernetes is a "cloud" skill; Docker/AWS in the experience text are the same family.
    [missing] = by_category(analyze(parsed_resume(), [target(i, required=("Kubernetes",)) for i in range(3)]), "MISSING_SKILL")
    assert missing.action == "add"
    assert "if you have" in missing.detail.lower()  # conditional: never claims the candidate has it


def test_missing_skill_is_learn_without_a_related_family_skill():
    parsed = parsed_resume()
    jobs = [target(i, required=("Python", "TensorFlow")) for i in range(3)]  # "ai" family: nothing related
    [missing] = by_category(analyze(parsed, jobs), "MISSING_SKILL")
    assert missing.action == "learn"
    assert missing.title == "Learn TensorFlow"


def test_missing_skill_uses_aliases_and_is_list_when_only_the_text_mentions_it():
    parsed = parsed_resume(skills=["Python", "Docker", "AWS", "FastAPI", "Redis"])  # no PostgreSQL in skills
    parsed["experience"][0]["description"] += "\n- Tuned postgres queries for the billing API."
    jobs = [target(i, required=("Python", "Postgres")) for i in range(3)]  # alias of PostgreSQL
    [missing] = by_category(analyze(parsed, jobs), "MISSING_SKILL")
    assert missing.id == "missing-skill-postgresql"
    assert missing.action == "list"


def test_missing_skill_not_raised_when_the_skill_is_listed_under_an_alias():
    parsed = parsed_resume(skills=["python3", "postgres", "Docker", "AWS"])
    assert not by_category(analyze(parsed, [target(i) for i in range(3)]), "MISSING_SKILL")


# --------------------------------------------------------------------------- KEYWORD_GAP


def test_keyword_gap_flags_frequent_terms_missing_from_the_resume():
    jobs = [target(i, description=f"Join our payments platform team {i}. Observability matters.") for i in range(3)]
    jobs.append(target(3, description="Internal tooling."))
    [gap] = by_category(analyze(parsed_resume(), jobs), "KEYWORD_GAP")
    terms = {e.label.split(":")[0] for e in gap.evidence}
    assert {"payments", "observability"} <= terms
    assert gap.priority == "LOW"  # fewer than four terms
    # stop words, skills, company names and words already on the resume are never keywords
    assert not terms & {"join", "our", "team", "python", "company0", "services", "reliable"}


def test_keyword_gap_ignores_boilerplate_shared_by_most_posts():
    template = "We are an equal opportunity employer committed to diversity and inclusion."
    jobs = [target(i, description=f"Payments platform role.\n{template}") for i in range(6)]
    [gap] = by_category(analyze(parsed_resume(), jobs), "KEYWORD_GAP")
    terms = {e.label.split(":")[0] for e in gap.evidence}
    assert "payments" in terms
    assert not terms & {"diversity", "inclusion", "committed", "opportunity"}


def test_keyword_gap_is_silent_when_the_resume_uses_the_words():
    jobs = [target(i, description="Build reliable systems that stay fast.") for i in range(3)]
    assert not by_category(analyze(parsed_resume(), jobs), "KEYWORD_GAP")


# --------------------------------------------------------------------------- WEAK_SUMMARY


def test_missing_summary_is_high():
    [weak] = by_category(analyze(parsed_resume(summary=None), [target(0)]), "WEAK_SUMMARY")
    assert weak.priority == "HIGH" and weak.id == "weak-summary"


def test_short_summary_lacking_title_years_and_skills():
    [weak] = by_category(analyze(parsed_resume(summary="Engineer who likes building things."), [target(0)]), "WEAK_SUMMARY")
    assert weak.priority == "MEDIUM"
    assert "only 5 words" in weak.detail
    assert "Backend Engineer" in weak.detail
    assert "4 years" in weak.detail
    assert "Python" in weak.detail and "PostgreSQL" in weak.detail
    assert weak.skills == ["Python", "PostgreSQL", "Docker"]  # the candidate's own skills, target-ranked


def test_summary_naming_a_same_family_title_counts_as_aligned():
    summary = (
        "Senior Backend Developer with 4 years of experience shipping Python and PostgreSQL services, owning "
        "schema design, Docker packaging and on-call, and keeping our systems reliable and fast as traffic grows "
        "every quarter."
    )
    assert not by_category(analyze(parsed_resume(summary=summary), [target(0)]), "WEAK_SUMMARY")


# --------------------------------------------------------------------------- EXPERIENCE_BULLETS


def test_bullet_helpers():
    assert rec.split_bullets("- one\n• two\n\n* three") == ["one", "two", "three"]
    assert rec.split_bullets(None) == []
    assert rec.has_outcome("Reduced costs") and rec.has_outcome("Served 10k users") and rec.has_outcome("Saved ₹2L")
    assert rec.has_outcome("Grew retention 5%")
    assert not rec.has_outcome("Maintained the billing service")


def test_current_role_without_bullets_is_high():
    parsed = parsed_resume()
    parsed["experience"][0]["description"] = ""
    [bullets] = by_category(analyze(parsed, [target(0)]), "EXPERIENCE_BULLETS")
    assert bullets.priority == "HIGH"
    assert bullets.id == "experience-bullets-northwind"


def test_mostly_outcome_free_bullets_are_medium_with_the_weak_bullets_as_evidence():
    parsed = parsed_resume()
    parsed["experience"][1]["description"] = "- Maintained services.\n- Wrote documentation.\n- Cut costs by 10%."
    [bullets] = by_category(analyze(parsed, [target(0)]), "EXPERIENCE_BULLETS")
    assert bullets.priority == "MEDIUM"
    assert "2 of 3 bullets" in bullets.detail
    assert [e.label for e in bullets.evidence if e.field == "experience[1].bullet"] == [
        "Maintained services.",
        "Wrote documentation.",
    ]


def test_more_than_eight_bullets_is_low():
    parsed = parsed_resume()
    parsed["experience"][1]["description"] = "\n".join(f"- Improved metric {i} by {i}%" for i in range(10))
    [bullets] = by_category(analyze(parsed, [target(0)]), "EXPERIENCE_BULLETS")
    assert bullets.priority == "LOW" and "10 bullets" in bullets.detail


# --------------------------------------------------------------------------- TITLE_ALIGNMENT


def test_unrelated_recent_title_is_flagged():
    parsed = parsed_resume()
    parsed["experience"][0]["title"] = "Marketing Associate"
    [title] = by_category(analyze(parsed, [target(0)]), "TITLE_ALIGNMENT")
    assert title.id == "title-alignment"
    assert title.priority in {"HIGH", "MEDIUM"}
    assert "Keep your real title" in title.detail  # never suggests changing a real title


def test_same_family_title_is_aligned():
    parsed = parsed_resume()
    parsed["experience"][0]["title"] = "Senior Python Developer"  # backend family
    assert not by_category(analyze(parsed, [target(0)]), "TITLE_ALIGNMENT")


# --------------------------------------------------------------------------- SECTION_MISSING


def test_missing_sections():
    parsed = parsed_resume(skills=[], education=[], projects=[], links={}, total_experience_years=1.0)
    found = {r.id: r.priority for r in by_category(analyze(parsed, [target(0)]), "SECTION_MISSING")}
    assert found == {
        "section-missing-skills": "HIGH",
        "section-missing-education": "MEDIUM",
        "section-missing-links": "MEDIUM",
        "section-missing-projects": "MEDIUM",
    }


def test_links_only_matter_for_software_roles_and_projects_only_for_juniors():
    parsed = parsed_resume(links={}, projects=[])
    jobs = [target(i, title="Sales Manager", required=("Negotiation",)) for i in range(2)]
    assert not by_category(analyze(parsed, jobs), "SECTION_MISSING")  # 4 years, non-software targets


# --------------------------------------------------------------------------- LENGTH_AND_FORMAT


def test_long_resume_for_junior_and_short_resume():
    long_text = "word " * 950
    junior = parsed_resume(total_experience_years=3.0)
    assert "format-too-long" in ids(analyze(junior, [target(0)], raw_text=long_text))
    senior = parsed_resume(total_experience_years=8.0)
    assert "format-too-long" not in ids(analyze(senior, [target(0)], raw_text=long_text))
    assert "format-too-short" in ids(analyze(parsed_resume(), [target(0)], raw_text="word " * 150))


def test_contact_details_and_dates():
    parsed = parsed_resume(email=None, phone=None)
    parsed["experience"][1]["start"] = None
    found = {r.id: r for r in by_category(analyze(parsed, [target(0)]), "LENGTH_AND_FORMAT")}
    assert found["format-contact-details"].priority == "HIGH"
    assert "email or phone number" in found["format-contact-details"].detail
    assert [e.field for e in found["format-missing-dates"].evidence] == ["experience[1]"]
    assert analyze(parsed_resume(phone=None), [target(0)]).recommendations[0].priority == "MEDIUM"


# --------------------------------------------------------------------------- STALE_CONTENT


def test_old_role_nobody_asks_for_is_stale_and_low():
    parsed = parsed_resume()
    parsed["experience"].append(
        {
            "company": "OldCo",
            "title": "PHP Developer",
            "start": "2012-01",
            "end": "2015-06",
            "description": "- Maintained PHP pages and Flash widgets.",
            "technologies": ["PHP"],
        }
    )
    parsed["skills"] = parsed["skills"] + ["PHP"]
    [stale] = by_category(analyze(parsed, [target(0)]), "STALE_CONTENT")
    assert stale.priority == "LOW"
    assert stale.skills == ["PHP"]
    assert any(e.field == "experience[2]" for e in stale.evidence)


def test_old_role_with_a_wanted_skill_is_not_stale():
    parsed = parsed_resume()
    parsed["experience"].append(
        {"company": "OldCo", "title": "Engineer", "start": "2012", "end": "2015", "description": "- Python ETL.", "technologies": ["Python"]}
    )
    assert not by_category(analyze(parsed, [target(0)]), "STALE_CONTENT")


# --------------------------------------------------------------------------- score maths


def _r(category: str, priority: str, n: int = 0) -> Recommendation:
    return Recommendation(id=f"{category}-{n}", category=category, priority=priority, title="t", detail="d")


def test_overall_score_weights_and_caps():
    assert rec.PRIORITY_PENALTY == {"HIGH": 12, "MEDIUM": 6, "LOW": 2}
    assert rec.overall_score([]) == 100
    assert rec.overall_score([_r("WEAK_SUMMARY", "HIGH")]) == 88
    assert rec.overall_score([_r("SECTION_MISSING", "MEDIUM"), _r("STALE_CONTENT", "LOW")]) == 92
    # five HIGH missing skills = 60, capped at 30
    assert rec.overall_score([_r("MISSING_SKILL", "HIGH", i) for i in range(5)]) == 70
    everything = [_r(c, "HIGH", i) for c in rec.CATEGORY_PENALTY_CAP for i in range(5)]
    assert rec.overall_score(everything) == max(0, 100 - sum(rec.CATEGORY_PENALTY_CAP.values()))


def test_recommendations_are_sorted_by_priority():
    parsed = parsed_resume(summary=None, links={"linkedin": "x"})
    order = [r.priority for r in analyze(parsed, [target(0)]).recommendations]
    assert order == sorted(order, key=rec.PRIORITY_RANK.__getitem__)


# --------------------------------------------------------------------------- projection


def test_match_score_matches_the_scoring_module():
    job = target(0, required=("Python", "Kubernetes"), salary_min=None)
    skills = ["Python"]
    expected = scoring.combine(
        skills=scoring.score_skills(["Python", "Kubernetes"], [], skills)[0],
        title=scoring.score_title("Backend Engineer", ["Backend Engineer"]),
        experience=scoring.score_experience(2.0, 6.0, 4.0)[0],
        location=scoring.score_location("Bangalore", None, ["Bangalore"], [])[0],
        salary=None,
        preference=scoring.score_preferences(
            work_mode=None,
            employment_type=None,
            job_skills=["Python", "Kubernetes"],
            preferred_work_modes=[],
            preferred_employment_types=[],
            preferred_technologies=[],
            excluded_keywords=[],
            text="Backend Engineer\nBuild reliable services.",
        )[0],
        priority="P2",
    )["score"]
    assert rec.match_score(job, INPUTS, skills, 4.0) == expected


def test_projection_adds_the_high_priority_skills_and_estimates_gains():
    jobs = [target(i, required=("Python", "PostgreSQL", "Kubernetes")) for i in range(4)]
    jobs += [target(4, required=("Python", "Go")), target(5)]
    analysis = analyze(parsed_resume(), jobs)
    projection = analysis.projection

    skills = rec.candidate_skills(INPUTS, rec.build_view(parsed_resume()))
    now = [rec.match_score(j, INPUTS, skills, 4.0) for j in jobs]
    after = [rec.match_score(j, INPUTS, skills + ["Kubernetes"], 4.0) for j in jobs]
    assert projection.current_average == round(sum(now) / len(now), 1)
    assert projection.projected_average == round(sum(after) / len(after), 1)
    assert projection.added_skills == ["Kubernetes"]  # Go is 1/6 jobs: not recommended
    assert projection.jobs_improved == 4
    assert projection.delta == round(projection.projected_average - projection.current_average, 1) > 0

    [kubernetes] = by_category(analysis, "MISSING_SKILL")
    assert kubernetes.estimated_score_gain == projection.delta
    assert all(r.estimated_score_gain == 0 for r in analysis.recommendations if r.category != "MISSING_SKILL")


def test_projection_without_targets_is_zero():
    analysis = analyze(parsed_resume(), [])
    assert analysis.projection.current_average == analysis.projection.projected_average == 0
    assert analysis.target_summary.jobs_analysed == 0


# --------------------------------------------------------------------------- cache


class _FakeResume:
    def __init__(self, resume_id: str, updated_at: datetime):
        self.id = resume_id
        self.updated_at = updated_at


def test_cache_key_tracks_resume_updates_and_target_jobs():
    t0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    jobs = [target(0, updated_at="a"), target(1, updated_at="b")]
    fp = rec.jobs_fingerprint(jobs, INPUTS)
    assert fp == rec.jobs_fingerprint(list(reversed(jobs)), INPUTS)  # order-insensitive
    assert fp != rec.jobs_fingerprint([target(0, updated_at="a"), target(1, updated_at="c")], INPUTS)
    assert fp != rec.jobs_fingerprint(jobs[:1], INPUTS)
    assert fp != rec.jobs_fingerprint(jobs, rec.MatchInputs(marker="prefs-changed"))
    assert rec.cache_key(_FakeResume("r1", t0), fp) != rec.cache_key(_FakeResume("r1", t0 + timedelta(seconds=1)), fp)


def test_cache_entries_expire_after_ten_minutes(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(rec, "_clock", lambda: now[0])
    key = ("r", "t", "fp")
    value = object()
    rec.cache_put(key, value)  # type: ignore[arg-type]
    now[0] += rec.CACHE_TTL_SECONDS - 1
    assert rec.cache_get(key) is value
    now[0] += 2
    assert rec.cache_get(key) is None
    assert rec.CACHE_TTL_SECONDS == 600


# --------------------------------------------------------------------------- AI polish task


def _sent() -> list[Recommendation]:
    parsed = parsed_resume(summary="Engineer.")
    parsed["experience"][1]["description"] = "- Maintained services.\n- Wrote documentation."
    return analyze(parsed, [target(0)]).recommendations


def test_mock_polish_drafts_text_from_resume_facts_only():
    parsed = parsed_resume(summary="Engineer.")
    parsed["experience"][1]["description"] = "- Maintained services.\n- Wrote documentation."
    analysis = analyze(parsed, [target(0)])
    result = ai_tasks.polish_resume_recommendations(analysis.resume_payload, analysis.recommendations)
    by_id = {item.id: item for item in result.items}
    assert set(by_id) == {r.id for r in analysis.recommendations}
    summary = by_id["weak-summary"].suggested_text
    assert summary.startswith("Backend Engineer with 4 years of experience")
    assert "Northwind" in summary
    bullet = by_id["experience-bullets-acme"].suggested_text
    assert bullet.startswith("Maintained services") and "[" in bullet  # placeholder, not an invented metric


class _FakeProvider:
    name = "fake"
    model = "fake-1"

    def __init__(self, result=None, error: Exception | None = None):
        self.result, self.error = result, error

    def supports_task(self, task_name: str) -> bool:
        return True

    def run_task(self, task_name: str, payload: dict) -> dict:
        if self.error:
            raise self.error
        return self.result


def test_polish_drops_unknown_ids_repeats_and_invented_numbers(monkeypatch):
    sent = _sent()
    known = sent[0].id
    provider = _FakeProvider(
        {
            "items": [
                {"id": known, "detail": "Clearer wording.", "suggested_text": "Engineer with 4 years of experience."},
                {"id": known, "detail": "Second copy must be ignored."},
                {"id": "made-up-id", "detail": "Not something we sent."},
                {"id": sent[1].id, "detail": "Boosted revenue by 37%.", "suggested_text": "Led a team of 15."},
            ]
        }
    )
    monkeypatch.setattr(ai_tasks, "get_llm_provider", lambda: provider)
    payload = analyze(parsed_resume(summary="Engineer."), [target(0)]).resume_payload
    result = ai_tasks.polish_resume_recommendations(payload, sent)
    assert [item.id for item in result.items] == [known, sent[1].id]
    assert result.items[0].detail == "Clearer wording."
    assert result.items[0].suggested_text == "Engineer with 4 years of experience."  # 4 is on the resume
    assert result.items[1].detail is None and result.items[1].suggested_text is None  # 37 / 15 are invented


def test_polish_clips_long_text(monkeypatch):
    sent = _sent()
    long_text = " ".join(["word"] * 100)
    monkeypatch.setattr(ai_tasks, "get_llm_provider", lambda: _FakeProvider({"items": [{"id": sent[0].id, "detail": long_text}]}))
    [item] = ai_tasks.polish_resume_recommendations({}, sent).items
    assert len(item.detail.split()) == ai_tasks.MAX_POLISH_WORDS


def test_polish_falls_back_to_deterministic_text_when_the_provider_raises(monkeypatch):
    analysis = analyze(parsed_resume(summary="Engineer."), [target(0)])
    original = copy.deepcopy([r.model_dump() for r in analysis.recommendations])
    monkeypatch.setattr(ai_tasks, "get_llm_provider", lambda: _FakeProvider(error=RuntimeError("model is down")))
    with pytest.raises(RuntimeError):
        ai_tasks.polish_resume_recommendations(analysis.resume_payload, analysis.recommendations)
    recs, polished, _ = rec.polish(analysis)
    assert polished is False
    assert [r.model_dump() for r in recs] == original


def test_polish_with_the_mock_marks_the_result_polished():
    analysis = analyze(parsed_resume(summary="Engineer."), [target(0)])
    recs, polished, provider = rec.polish(analysis)
    assert polished is True and provider == "mock"
    assert next(r for r in recs if r.id == "weak-summary").suggested_text


def test_mock_provider_answers_the_task_through_the_prompt_envelope():
    from app.modules.ai.prompts import build_prompt
    from app.modules.ai.schemas import PolishedRecommendations

    payload = {"resume": {"recent_title": "Engineer"}, "recommendations": [{"id": "weak-summary", "category": "WEAK_SUMMARY", "detail": "x"}]}
    prompt = build_prompt("polish_resume_recommendations", payload, schema=PolishedRecommendations)
    assert "do not add employers, dates, degrees or metrics" in prompt.lower()
    data = MockLLMProvider().complete_json(prompt, schema=PolishedRecommendations)
    assert data["items"][0]["id"] == "weak-summary"


# --------------------------------------------------------------------------- API


def _user(db: Session, email: str) -> User:
    user = User(email=email, hashed_password=hash_password("StrongPass123!"), full_name="Asha Rao", is_active=True)
    db.add(user)
    db.flush()
    return user


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}


def _job(db: Session, title: str, company: str, required: list[str]) -> Job:
    normalized = company.lower()
    row = db.scalars(select(Company).where(Company.normalized_name == normalized)).first()
    if row is None:
        row = Company(name=company, normalized_name=normalized)
        db.add(row)
        db.flush()
    job = Job(
        company_id=row.id,
        title=title,
        normalized_title=title.lower(),
        description="Own payments services end to end.",
        location="Bangalore",
        normalized_location="bangalore",
        work_mode=WorkMode.HYBRID,
        employment_type=EmploymentType.FULL_TIME,
        experience_min=1.0,
        experience_max=4.0,
        required_skills=required,
        preferred_skills=[],
        posted_at=datetime.now(timezone.utc),
        dedupe_hash=compute_dedupe_hash(normalized, title.lower(), "bangalore"),
    )
    db.add(job)
    db.flush()
    return job


@pytest.fixture
def seeded(db: Session):
    owner = _user(db, "asha@example.com")
    db.add(UserProfile(user_id=owner.id, years_of_experience=2.0))
    db.add(JobPreference(user_id=owner.id, desired_titles=["Backend Engineer"], preferred_locations=["Bangalore"]))
    db.flush()
    resume = resume_service.create_resume_from_bytes(db, owner.id, "asha.pdf", build_pdf())
    jobs = [_job(db, "Backend Engineer", f"Co{i}", ["Node.js", "PostgreSQL", "Kubernetes"]) for i in range(3)]
    jobs.append(_job(db, "Backend Engineer", "Co3", ["Python"]))
    matching_service.analyze_jobs(db, owner.id, jobs)
    other = _user(db, "other@example.com")
    db.commit()
    return {"owner": owner, "other": other, "resume_id": str(resume.id)}


def test_recommendations_endpoint(client: TestClient, seeded):
    client.headers.update(_headers(seeded["owner"]))
    url = f"{RESUMES}/{seeded['resume_id']}/recommendations"
    response = client.get(url)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["resume_id"] == seeded["resume_id"]
    assert body["target_summary"]["jobs_analysed"] == 4
    assert 0 <= body["overall_score"] <= 100
    assert body["ai_polished"] is True and body["ai_provider"] == "mock"
    assert body["cached"] is False
    kubernetes = next(r for r in body["recommendations"] if r["id"] == "missing-skill-kubernetes")
    assert kubernetes["priority"] == "HIGH" and kubernetes["action"] == "add"
    assert kubernetes["estimated_score_gain"] > 0
    projection = body["score_projection"]
    assert projection["added_skills"] == ["Kubernetes"]
    assert projection["projected_average"] > projection["current_average"]
    assert [v["version_number"] for v in body["version_history"]] == [1]

    assert client.get(url).json()["cached"] is True
    assert client.get(url, params={"refresh": "true"}).json()["cached"] is False


def test_history_tracks_versions_before_and_after(client: TestClient, seeded):
    client.headers.update(_headers(seeded["owner"]))
    base = f"{RESUMES}/{seeded['resume_id']}"
    before = client.get(f"{base}/recommendations").json()  # warms the cache

    parsed = client.get(base).json()["parsed_data"]
    parsed["skills"] = parsed["skills"] + ["Kubernetes"]
    assert client.put(f"{base}/parsed-data", json=parsed).status_code == 200

    history = client.get(f"{base}/recommendations/history")
    assert history.status_code == 200, history.text
    v1, v2 = history.json()
    assert (v1["version_number"], v2["version_number"]) == (1, 2)
    assert v2["is_current"] and not v1["is_current"]
    assert v2["average_match_score"] > v1["average_match_score"]
    assert v2["overall_score"] >= v1["overall_score"]

    after = client.get(f"{base}/recommendations").json()  # resume.updated_at moved: cache miss
    assert after["cached"] is False
    assert "missing-skill-kubernetes" not in {r["id"] for r in after["recommendations"]}
    assert after["score_projection"]["current_average"] == before["score_projection"]["projected_average"]


def test_another_users_resume_is_not_found(client: TestClient, seeded):
    client.headers.update(_headers(seeded["other"]))
    base = f"{RESUMES}/{seeded['resume_id']}"
    for path in ("/recommendations", "/recommendations/history"):
        response = client.get(base + path)
        assert response.status_code == 404, path
        assert response.json()["error"]["code"]


def test_recommendations_require_authentication(client: TestClient, seeded):
    assert client.get(f"{RESUMES}/{seeded['resume_id']}/recommendations").status_code == 401


def test_no_target_jobs_still_returns_resume_advice(client: TestClient, db: Session):
    user = _user(db, "solo@example.com")
    resume = resume_service.create_resume_from_bytes(db, user.id, "cv.pdf", build_pdf())
    db.commit()
    client.headers.update(_headers(user))
    body = client.get(f"{RESUMES}/{resume.id}/recommendations").json()
    assert body["target_summary"]["jobs_analysed"] == 0
    assert body["score_projection"]["current_average"] == 0
    assert not [r for r in body["recommendations"] if r["category"] in {"MISSING_SKILL", "KEYWORD_GAP"}]
