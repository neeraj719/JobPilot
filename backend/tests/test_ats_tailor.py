"""Job-specific resumes in one call (``POST /ats/targets/tailor``) and the AI tailoring pass.

The quick-tailor endpoint: pasted JD + explicit / default resume, no resume at all, company and
role derived from the JD (two different JDs both save; the same JD twice is ``target_exists``),
ownership. The tailoring pass (``ats.tailoring``) against a fake model: guard-passing rewrites
are applied as a new version of the tailored copy, a rewrite that adds a number is rejected, the
source resume never moves; no model -> rules-only and DONE; a model error -> the rule-based copy
stands and the error is on the analysis; the retry re-runs the tailoring task.
"""
from __future__ import annotations

import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ats import AtsAnalysis, JobTarget, OptimizationSuggestion
from app.models.enums import AtsAnalysisStatus, ResumeChangeSource, ResumeKind, SuggestionStatus
from app.models.profile import UserProfile
from app.models.resume import Resume, ResumeVersion
from app.modules.ats import llm
from app.modules.ats import service as ats_service
from app.modules.ats import tailoring
from app.modules.ats.schemas import StructuredJD
from app.modules.ats.suggestions import make_facts
from app.modules.resumes import recommendations as rec_mod

try:
    from helpers.ats import BACKEND_JD, FRONTEND_JD, backend_resume, frontend_resume, headers, make_resume, make_user, no_page_network  # noqa: F401
except ImportError:  # pragma: no cover
    from tests.helpers.ats import BACKEND_JD, FRONTEND_JD, backend_resume, frontend_resume, headers, make_resume, make_user, no_page_network  # type: ignore[no-redef]  # noqa: F401

pytestmark = pytest.mark.usefixtures("no_page_network")

ATS = "/api/v1/ats"

#: A posting that names neither a company nor a heading title the parser takes as the role.
NO_COMPANY_JD = """We are hiring a data analyst to join a growing team.

Responsibilities
- Build dashboards in SQL and Python for the operations team
- Clean and model data from several internal sources
- Present findings to product managers every week

Requirements
- 2+ years of experience with SQL and Python
- Experience with Tableau or Power BI
"""


@pytest.fixture(autouse=True)
def _fresh_cache():
    rec_mod.clear_cache()
    yield
    rec_mod.clear_cache()


@pytest.fixture
def owner(db: Session):
    user = make_user(db, "tailor.owner@example.com")
    db.add(UserProfile(user_id=user.id, full_name="Asha Rao", skills=["Kubernetes"], years_of_experience=4.5))
    first = make_resume(db, user, name="Backend resume")
    second = make_resume(db, user, frontend_resume(), name="Frontend resume")
    db.commit()
    return {"user": user, "headers": headers(user), "resume_id": str(first.id), "second_id": str(second.id)}


def _quick(client: TestClient, owner: dict, **body) -> dict:
    payload = {"jd": {"source": "PASTED", "text": BACKEND_JD}} | body
    r = client.post(f"{ATS}/targets/tailor", json=payload, headers=owner["headers"])
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- the endpoint


def test_quick_tailor_with_pasted_jd_and_an_explicit_resume(client: TestClient, owner: dict, db: Session):
    result = _quick(client, owner, source_resume_id=owner["resume_id"], company_name="Acme", role_title="Senior Backend Engineer")
    assert result["target_id"] == result["target"]["id"]
    assert result["tailored_resume_id"] == result["resume"]["id"] and result["analysis_id"] == result["analysis"]["id"]
    assert result["target"]["company_name"] == "Acme" and result["target"]["role_title"] == "Senior Backend Engineer"
    assert result["target"]["status"] == "READY" and result["target"]["tailored_resume"]["id"] == result["resume"]["id"]
    assert result["resume"]["kind"] == "TAILORED" and result["resume"]["source_resume_id"] == owner["resume_id"]
    assert result["resume"]["name"] == "Backend resume — Acme Senior Backend Engineer"
    assert result["ai_pass"] == "rules_only" and result["analysis"]["status"] == "DONE"  # mock provider
    assert result["analysis"]["overall_score"] > result["source_score"]
    target = db.get(JobTarget, uuid.UUID(result["target_id"]))
    assert target.latest_snapshot_id is not None and target.source_resume_id == uuid.UUID(owner["resume_id"])


def test_quick_tailor_without_a_resume_uses_the_default(client: TestClient, owner: dict, db: Session):
    default = db.scalar(select(Resume).where(Resume.user_id == owner["user"].id, Resume.is_default.is_(True)))
    assert default is not None
    result = _quick(client, owner, company_name="Acme", role_title="Backend Engineer")
    assert result["resume"]["source_resume_id"] == str(default.id)


def test_quick_tailor_with_the_second_resume(client: TestClient, owner: dict):
    result = _quick(client, owner, source_resume_id=owner["second_id"], jd={"source": "PASTED", "text": FRONTEND_JD})
    assert result["resume"]["source_resume_id"] == owner["second_id"]


def test_quick_tailor_needs_a_resume(client: TestClient, db: Session):
    user = make_user(db, "tailor.empty@example.com")
    db.commit()
    r = client.post(f"{ATS}/targets/tailor", json={"jd": {"source": "PASTED", "text": BACKEND_JD}}, headers=headers(user))
    assert r.status_code == 422 and r.json()["error"]["code"] == "resume_required"
    assert db.scalar(select(JobTarget).where(JobTarget.user_id == user.id)) is None


def test_quick_tailor_needs_a_job_description(client: TestClient, owner: dict):
    r = client.post(f"{ATS}/targets/tailor", json={"jd": {"source": "PASTED", "text": "  "}}, headers=owner["headers"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "jd_required"


def test_company_and_role_are_derived_and_two_pasted_jds_both_save(client: TestClient, owner: dict):
    first = _quick(client, owner, jd={"source": "PASTED", "text": NO_COMPANY_JD})
    assert first["target"]["company_name"] == "Unknown company"
    assert first["target"]["role_title"]  # the JD's first heading line, or "Untitled role"
    second = _quick(client, owner, jd={"source": "PASTED", "text": NO_COMPANY_JD.replace("data analyst", "data analyst (contract)")})
    assert second["target_id"] != first["target_id"]  # same derived name, different posting: no collision
    assert second["target"]["company_name"] == "Unknown company"
    backend = _quick(client, owner, jd={"source": "PASTED", "text": BACKEND_JD})
    assert backend["target"]["role_title"] == "Senior Backend Engineer"


def test_the_same_jd_twice_is_target_exists(client: TestClient, owner: dict, db: Session):
    first = _quick(client, owner, jd={"source": "PASTED", "text": NO_COMPANY_JD})
    r = client.post(f"{ATS}/targets/tailor", json={"jd": {"source": "PASTED", "text": NO_COMPANY_JD}}, headers=owner["headers"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "target_exists"
    assert r.json()["error"]["details"]["id"] == first["target_id"]
    # Nothing half-made is left behind: still one target, one tailored copy.
    assert len(list(db.scalars(select(JobTarget).where(JobTarget.user_id == owner["user"].id)))) == 1
    tailored = db.scalars(select(Resume).where(Resume.user_id == owner["user"].id, Resume.kind == ResumeKind.TAILORED))
    assert len(list(tailored)) == 1
    # The saved target is tailored again through its own endpoint.
    again = client.post(f"{ATS}/targets/{first['target_id']}/tailor", json={"source_resume_id": owner["second_id"]}, headers=owner["headers"])
    assert again.status_code == 200, again.text
    assert again.json()["target_id"] == first["target_id"] and again.json()["ai_pass"] == "rules_only"


def test_typed_company_and_role_keep_the_plain_key(client: TestClient, owner: dict):
    _quick(client, owner, company_name="Globex", role_title="Platform Engineer")
    r = client.post(
        f"{ATS}/targets/tailor",
        json={"jd": {"source": "PASTED", "text": FRONTEND_JD}, "company_name": "Globex", "role_title": "Platform Engineer"},
        headers=owner["headers"],
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "target_exists"


def test_another_users_resume_is_not_found(client: TestClient, owner: dict, db: Session):
    stranger = make_user(db, "tailor.stranger@example.com")
    theirs = make_resume(db, stranger, name="Theirs")
    db.commit()
    r = client.post(
        f"{ATS}/targets/tailor", json={"jd": {"source": "PASTED", "text": BACKEND_JD}, "source_resume_id": str(theirs.id)}, headers=owner["headers"]
    )
    assert r.status_code == 404
    assert db.scalar(select(JobTarget).where(JobTarget.user_id == owner["user"].id)) is None


# --------------------------------------------------------------------------- the AI pass (fake model)


@pytest.fixture
def fake_model(monkeypatch):
    """A configured model whose background thread does not start (the test runs the pass itself)."""
    started: list[tuple] = []
    monkeypatch.setattr(llm, "model_available", lambda *a, **k: True)
    monkeypatch.setattr(llm, "model_info", lambda task=None: ("fake", "fake-1"))
    monkeypatch.setattr(ats_service, "start_polish", lambda analysis_id, user_id, *, task=None: started.append((analysis_id, task)))
    return started


def _bullet_in(prompt: str) -> str:
    match = re.search(r"BEGIN_UNTRUSTED RESUME_BULLET>>>\n(.*?)\n<<<END_UNTRUSTED", prompt, re.S)
    assert match, prompt
    return match.group(1).strip()


GOOD_SUMMARY = "Backend Engineer with 4.5 years of experience working with Python, PostgreSQL and Docker. Seeking Senior Backend Engineer roles."


def _fake_answers(task: str, prompt: str, **_kw) -> dict:
    assert task == llm.TASK_TAILOR
    if "RESUME_SUMMARY" in prompt:
        return {"summary": GOOD_SUMMARY}
    bullet = _bullet_in(prompt)
    if "report generation" in bullet:
        return {"bullet": bullet.rstrip(".") + " across 37 services."}  # adds a number: must be rejected
    return {"bullet": bullet.rstrip(".") + " for the payments platform."}


def test_tailoring_pass_applies_guard_passing_rewrites_as_a_new_version(
    client: TestClient, owner: dict, db: Session, monkeypatch, fake_model
):
    result = _quick(client, owner, source_resume_id=owner["resume_id"], company_name="Acme", role_title="Senior Backend Engineer")
    assert result["ai_pass"] == "running" and result["analysis"]["status"] == "RUNNING"
    assert fake_model == [(uuid.UUID(result["analysis_id"]), llm.TASK_TAILOR)]
    monkeypatch.setattr(llm, "llm_json", _fake_answers)

    ats_service.polish_analysis(uuid.UUID(result["analysis_id"]), task=llm.TASK_TAILOR)
    db.expire_all()

    tailored = db.get(Resume, uuid.UUID(result["tailored_resume_id"]))
    assert tailored.current_version == 2
    latest = db.scalar(select(ResumeVersion).where(ResumeVersion.resume_id == tailored.id, ResumeVersion.version_number == 2))
    assert latest.change_source == ResumeChangeSource.AI and latest.note.startswith("AI tailoring for Acme · Senior Backend Engineer:")
    assert tailored.parsed_data["summary"] == GOOD_SUMMARY
    description = tailored.parsed_data["experience"][0]["description"]
    assert "for the payments platform." in description
    assert "37 services" not in description  # rejected
    assert db.get(Resume, uuid.UUID(owner["resume_id"])).current_version == 1  # the source never moves

    analysis = db.get(AtsAnalysis, uuid.UUID(result["analysis_id"]))
    assert analysis.status == AtsAnalysisStatus.DONE and analysis.error is None and analysis.progress == 100
    rows = [s for s in analysis.suggestions if (s.checks or {}).get("tailor_pass")]
    assert len(rows) <= 1 + tailoring.TAILOR_MAX_BULLETS + 1
    applied = [s for s in rows if s.status == SuggestionStatus.APPLIED]
    assert applied and all(s.applied_version == 2 and s.checks["applied_to_resume_id"] == str(tailored.id) for s in applied)
    rejected = [s for s in rows if s.checks.get("ai_rejected")]
    assert [s.checks["ai_rejected"] for s in rejected] == ["invented_number"]
    assert all(s.status != SuggestionStatus.APPLIED for s in rejected)

    target = db.get(JobTarget, uuid.UUID(result["target_id"]))
    final = db.get(AtsAnalysis, target.last_analysis_id)
    assert final.id != analysis.id and final.resume_version == 2 and final.status == AtsAnalysisStatus.DONE
    assert final.ai_provider == "fake" and target.tailored_resume_version == 2

    compare = client.get(f"{ATS}/targets/{target.id}/compare", headers=owner["headers"]).json()
    groups = {c["group"]: c for c in compare["changes"]}
    assert groups["summary"]["source"] == "AI" and groups["summary"]["after"] == GOOD_SUMMARY
    assert any(c["group"] == "bullets" and c["source"] == "AI" and "payments platform" in c["after"] for c in compare["changes"])
    assert "skills" in groups  # the rule-based "list Kubernetes" from the profile
    assert compare["ai_rejected"] == 1 and compare["tailored"]["version"] == 2

    polled = client.get(f"{ATS}/analyses/{analysis.id}", headers=owner["headers"]).json()
    states = [s["checks"]["tailor_state"] for s in polled["suggestions"] if s["checks"].get("tailor_pass")]
    assert "pending" not in states


def test_a_rule_tidied_bullet_rewritten_by_the_ai_is_one_change(client: TestClient, owner: dict, db: Session, monkeypatch, fake_model):
    result = _quick(client, owner, source_resume_id=owner["resume_id"], company_name="Acme", role_title="Senior Backend Engineer")
    monkeypatch.setattr(llm, "llm_json", _fake_answers)
    ats_service.polish_analysis(uuid.UUID(result["analysis_id"]), task=llm.TASK_TAILOR)
    compare = client.get(f"{ATS}/targets/{result['target_id']}/compare", headers=owner["headers"]).json()
    chained = [c for c in compare["changes"] if c["group"] == "bullets" and c["before"] and c["before"].startswith("Worked on REST APIs")]
    assert len(chained) == 1 and chained[0]["after"].endswith("for the payments platform.") and len(chained[0]["suggestion_ids"]) == 2


def test_no_model_means_rules_only_and_done(client: TestClient, owner: dict, db: Session):
    result = _quick(client, owner, company_name="Acme", role_title="Senior Backend Engineer")
    assert result["ai_pass"] == "rules_only" and result["analysis"]["status"] == "DONE" and result["analysis"]["error"] is None
    assert db.get(Resume, uuid.UUID(result["tailored_resume_id"])).current_version == 1
    assert not [s for s in result["analysis"]["suggestions"] if s["checks"].get("tailor_pass")]


def test_a_model_error_keeps_the_rule_based_copy(client: TestClient, owner: dict, db: Session, monkeypatch, fake_model):
    result = _quick(client, owner, company_name="Acme", role_title="Senior Backend Engineer")

    def down(*_a, **_kw):
        raise RuntimeError("provider_timeout: the model took too long")

    monkeypatch.setattr(llm, "llm_json", down)
    ats_service.polish_analysis(uuid.UUID(result["analysis_id"]), task=llm.TASK_TAILOR)
    db.expire_all()
    tailored = db.get(Resume, uuid.UUID(result["tailored_resume_id"]))
    assert tailored is not None and tailored.current_version == 1  # the rule-based copy stands
    polled = client.get(f"{ATS}/analyses/{result['analysis_id']}", headers=owner["headers"]).json()
    assert polled["status"] == "DONE" and polled["error"].startswith("The AI rewrite did not run: provider_timeout")
    states = {s["checks"]["tailor_state"] for s in polled["suggestions"] if s["checks"].get("tailor_pass")}
    assert states == {"not_run"}

    # Retry: inferred as the tailoring task (the analysis is a tailored copy's first one).
    fake_model.clear()
    r = client.post(f"{ATS}/analyses/{result['analysis_id']}/polish", headers=owner["headers"])
    assert r.status_code == 200 and r.json()["status"] == "RUNNING" and r.json()["error"] is None
    assert fake_model == [(uuid.UUID(result["analysis_id"]), llm.TASK_TAILOR)]
    monkeypatch.setattr(llm, "llm_json", _fake_answers)
    ats_service.polish_analysis(uuid.UUID(result["analysis_id"]), task=llm.TASK_TAILOR)
    db.expire_all()
    assert db.get(Resume, uuid.UUID(result["tailored_resume_id"])).current_version == 2


def test_retry_of_a_plain_analysis_stays_the_polish_task(client: TestClient, owner: dict, fake_model):
    analysis = client.post(
        f"{ATS}/analyses", json={"resume_id": owner["resume_id"], "jd": {"text": BACKEND_JD}}, headers=owner["headers"]
    ).json()
    fake_model.clear()
    r = client.post(f"{ATS}/analyses/{analysis['id']}/polish", headers=owner["headers"])
    assert r.status_code == 200
    assert fake_model == [(uuid.UUID(analysis["id"]), llm.TASK_POLISH)]


def test_the_pass_skips_a_copy_edited_meanwhile(client: TestClient, owner: dict, db: Session, monkeypatch, fake_model):
    result = _quick(client, owner, company_name="Acme", role_title="Senior Backend Engineer")
    tailored_id = result["tailored_resume_id"]
    parsed = db.get(Resume, uuid.UUID(tailored_id)).parsed_data
    r = client.put(f"/api/v1/resumes/{tailored_id}/parsed-data", json=parsed | {"summary": "My own words."}, headers=owner["headers"])
    assert r.status_code == 200, r.text
    monkeypatch.setattr(llm, "llm_json", _fake_answers)
    ats_service.polish_analysis(uuid.UUID(result["analysis_id"]), task=llm.TASK_TAILOR)
    db.expire_all()
    tailored = db.get(Resume, uuid.UUID(tailored_id))
    assert tailored.current_version == 2 and tailored.parsed_data["summary"] == "My own words."
    analysis = db.get(AtsAnalysis, uuid.UUID(result["analysis_id"]))
    assert analysis.status == AtsAnalysisStatus.DONE and "changed" in (analysis.error or "")


# --------------------------------------------------------------------------- guards and planning (pure)


BACKEND_STRUCTURED = StructuredJD(title="Senior Backend Engineer", company="Acme", required_skills=["Python", "Go", "PostgreSQL"], preferred_skills=["Kafka"])


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        (GOOD_SUMMARY, None),
        ("Senior Backend Engineer with 4.5 years of experience in Python.", "claimed_title"),
        ("Backend Engineer with 9 years of experience in Python.", "invented_number"),
        ("Backend Engineer at Google with experience in Python and PostgreSQL.", "invented_name"),
        ("Backend Engineer who led a team building Python services.", "invented_claim"),
        ("Backend Engineer with Kubernetes and Python experience.", "invented_skill"),
        (" ".join(["Python"] * 61), "too_long"),
    ],
)
def test_summary_guard(db: Session, text: str, problem: str | None):
    user = make_user(db, f"tailor.guard.{uuid.uuid4().hex[:6]}@example.com")
    db.commit()
    facts = make_facts(backend_resume(), "", rec_mod.load_match_inputs(db, user.id))
    assert tailoring.summary_problem(text, facts, BACKEND_STRUCTURED) == problem


def test_bullet_guard_refuses_a_tool_its_entry_does_not_name(db: Session):
    user = make_user(db, "tailor.bullet@example.com")
    db.commit()
    parsed = backend_resume()
    facts = make_facts(parsed, "", rec_mod.load_match_inputs(db, user.id))
    entry = parsed["experience"][1]  # Initech: Python and Kafka only
    original = "Built internal tools in Python"
    assert tailoring.bullet_problem("Built internal tools in Python for the support team.", original, entry, facts) is None
    # Django is on the resume (another role), but not in this entry: not allowed here.
    assert tailoring.bullet_problem("Built internal tools in Python and Django.", original, entry, facts) == "invented_skill"


def test_plan_bullets_puts_the_matching_entries_first_and_caps():
    parsed = backend_resume()
    plan = tailoring.plan_bullets(parsed, BACKEND_STRUCTURED)
    assert plan[0][0] == 0  # Globex names Python, PostgreSQL, Django
    assert {index for index, _ in plan} == {0, 1}
    many = backend_resume()
    many["experience"][0]["description"] = "\n".join(f"- Built Python service number{n} for billing" for n in range(20))
    assert len(tailoring.plan_bullets(many, BACKEND_STRUCTURED)) == tailoring.TAILOR_MAX_BULLETS


@pytest.mark.parametrize(
    ("text", "company"),
    [
        (BACKEND_JD, "Acme"),  # an "About Acme" heading
        ("Senior Data Engineer at Northwind Traders\n\nResponsibilities\n- Build pipelines", "Northwind Traders"),
        ("Join Contoso as a Staff Engineer.\n", "Contoso"),
        ("At Fabrikam, we ship every day.\n", "Fabrikam"),
        ("Acme Corp is hiring a backend engineer\n", "Acme Corp"),
        ("About the role\nYou will build things.", None),
        ("About us\nWe build things.", None),
        (NO_COMPANY_JD, None),
        (FRONTEND_JD, None),
    ],
)
def test_the_jd_parser_reads_a_plainly_named_company(text: str, company: str | None):
    from app.modules.ats.jd import structure_jd

    assert structure_jd(text).company == company
    assert structure_jd(text, company="Typed Inc").company == "Typed Inc"  # what the user typed always wins
