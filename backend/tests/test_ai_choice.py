"""ai-model-choice: "which model should process this?" — candidates, per-run override, prompt mode.

No network: providers are stubs injected through ``runtime.construct_provider``; the local
Ollama listing is replaced through ``choice._ollama_models``.
"""
from __future__ import annotations

import io
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import encrypt_str
from app.models.ai_settings import (
    AiCredentialStatus,
    AiProviderCredential,
    AiProviderSettings,
    AiUsageEvent,
    AiUsageStatus,
)
from app.models.ats import AtsAnalysis
from app.models.profile import UserProfile
from app.modules.ai import base_url as base_url_mod
from app.modules.ai import choice, context, routing, runtime, settings_service
from app.modules.ai.errors import AIProviderError
from app.modules.ai.provider import LLMProvider, report_usage
from app.modules.ai.providers.mock import MockLLMProvider
from app.modules.resumes import recommendations as rec_mod

try:
    from helpers.ats import BACKEND_JD, headers, make_resume, make_user, no_page_network  # noqa: F401
except ImportError:  # pragma: no cover
    from tests.helpers.ats import BACKEND_JD, headers, make_resume, make_user, no_page_network  # type: ignore[no-redef]  # noqa: F401

pytestmark = pytest.mark.usefixtures("no_page_network")

AI = "/api/v1/ai"
ATS = "/api/v1/ats"
STUB_URL = "http://localhost:8102/v1"
STUB_MODEL = "stub-json-1"
MOCK_ID = "mock:mock-deterministic-v1"


# --------------------------------------------------------------------------- stubs


class StubProvider(LLMProvider):
    """Answers every JSON prompt with a shape the ATS prompts accept; records each call."""

    def __init__(self, name: str, model: str, calls: list[dict[str, Any]], *, fail: bool = False, models: list[str] | None = None) -> None:
        self.name, self.model, self._calls, self._fail = name, model, calls, fail
        self._models = models

    def _go(self, kind: str, prompt: str) -> Any:
        self._calls.append({"provider": self.name, "model": self.model, "kind": kind, "prompt": prompt[:80]})
        if self._fail:
            raise AIProviderError("provider_timeout", "stub timed out", provider=self.name, model=self.model)
        report_usage(50, 10)
        return {
            "bullet": "Designed and built Python microservices on Kubernetes.",
            "title": None,
            "required_skills": [],
            "preferred_skills": [],
            "keywords": [],
        }

    def complete(self, prompt, *, system=None, max_tokens=800, temperature=0.2):  # noqa: ANN001, ANN201
        self._go("text", prompt)
        return "ok"

    def complete_json(self, prompt, *, schema=None, system=None, max_tokens=1500):  # noqa: ANN001, ANN201
        return self._go("json", prompt)

    def list_models(self) -> list[dict[str, Any]] | None:
        return [{"id": m} for m in (self._models if self._models is not None else [STUB_MODEL, "stub-json-2"])]


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"calls": [], "built": [], "ollama": None, "fail": set()}

    def construct(provider: str, model: str, *, api_key: str | None = None, base_url: str | None = None) -> LLMProvider:
        state["built"].append({"provider": provider, "model": model, "base_url": base_url})
        if provider == "mock":
            return MockLLMProvider()
        return StubProvider(provider, model, state["calls"], fail=(provider, model) in state["fail"])

    monkeypatch.setattr(runtime, "construct_provider", construct)
    monkeypatch.setattr(choice, "_ollama_models", lambda user, cred: state["ollama"])
    monkeypatch.setattr(settings, "AI_ALLOW_HOSTED_PROVIDERS", True)
    monkeypatch.setattr(settings, "AI_ALLOW_LOCAL_BASE_URLS", True)
    base_url_mod.set_resolver(lambda host: ["127.0.0.1"] if host in ("localhost",) else ["93.184.215.14"])
    runtime.clear_client_cache()
    settings_service._model_cache.clear()
    choice.invalidate_choices()
    rec_mod.clear_cache()
    yield state
    base_url_mod.set_resolver(None)
    runtime.clear_client_cache()
    settings_service._model_cache.clear()
    choice.invalidate_choices()
    rec_mod.clear_cache()


@pytest.fixture
def owner(db: Session) -> dict[str, Any]:
    user = make_user(db, f"choice-{uuid.uuid4().hex[:6]}@example.com")
    db.add(UserProfile(user_id=user.id, full_name="Asha Rao", skills=["Kubernetes"], years_of_experience=4.5))
    resume = make_resume(db, user)
    db.commit()
    return {"user": user, "headers": headers(user), "resume_id": str(resume.id)}


def _stub_credential(db: Session, user, *, status: AiCredentialStatus = AiCredentialStatus.OK, last_error: str | None = None) -> None:
    db.add(
        AiProviderCredential(
            user_id=user.id, provider="openai_compatible", base_url=STUB_URL, credential_version=1, status=status, last_error=last_error
        )
    )
    db.commit()


def _openai_credential(db: Session, user) -> None:
    key = "sk-test-key-1234"
    db.add(
        AiProviderCredential(
            user_id=user.id, provider="openai", encrypted_api_key=encrypt_str(key), key_hint=key[-4:], credential_version=1,
            status=AiCredentialStatus.OK,
        )
    )
    db.commit()


def _settings(db: Session, user, **fields: Any) -> AiProviderSettings:
    row = AiProviderSettings(user_id=user.id, workflow_models=fields.pop("workflow_models", {}), **fields)
    db.add(row)
    db.commit()
    return row


def _choices(client: TestClient, owner: dict, task: str = "analyze_resume_fit") -> dict[str, Any]:
    r = client.get(f"{AI}/choices", params={"task": task}, headers=owner["headers"])
    assert r.status_code == 200, r.text
    return r.json()


def _events(db: Session, user) -> list[AiUsageEvent]:
    db.expire_all()
    return list(db.scalars(select(AiUsageEvent).where(AiUsageEvent.user_id == user.id).order_by(AiUsageEvent.created_at)))


STUB_CHOICE = {"provider": "openai_compatible", "model": STUB_MODEL}


# --------------------------------------------------------------------------- candidates


def test_one_usable_model_never_asks(client: TestClient, owner: dict, stub: dict) -> None:
    body = _choices(client, owner)
    assert body["task"] == "analyze_resume_fit" and body["workflow"] == "analysis"
    assert body["mode"] == "ask"
    assert len(body["candidates"]) == 1
    only = body["candidates"][0]
    assert only["id"] == MOCK_ID == body["default"] and only["is_default"] is True
    assert only["source"] == "server_default" and only["available"] is True
    assert only["cost_hint"] == "free, local"
    assert body["usable_count"] == 1 and body["should_ask"] is False


def test_zero_usable_models_when_the_default_has_no_key(client: TestClient, owner: dict, stub: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    body = _choices(client, owner)
    assert body["usable_count"] == 0 and body["should_ask"] is False
    assert body["candidates"][0]["id"] == "openai:gpt-4o-mini"
    assert body["candidates"][0]["available"] is False and "API key" in body["candidates"][0]["unavailable_reason"]


def test_two_or_more_usable_models_ask(client: TestClient, owner: dict, stub: dict, db: Session) -> None:
    _stub_credential(db, owner["user"])
    stub["ollama"] = ["qwen2.5:3b-instruct", "llama3.2:1b"]
    body = _choices(client, owner)
    ids = [c["id"] for c in body["candidates"]]
    assert ids[0] == MOCK_ID
    assert f"openai_compatible:{STUB_MODEL}" in ids
    assert "ollama:qwen2.5:3b-instruct" in ids and "ollama:llama3.2:1b" in ids
    assert body["usable_count"] == 4 and body["should_ask"] is True
    by_id = {c["id"]: c for c in body["candidates"]}
    assert by_id["ollama:qwen2.5:3b-instruct"]["source"] == "local"
    assert by_id["ollama:qwen2.5:3b-instruct"]["label"] == "Qwen 2.5 3B Instruct"
    stub_entry = by_id[f"openai_compatible:{STUB_MODEL}"]
    assert stub_entry["source"] == "credential" and stub_entry["hosted"] is False
    assert stub_entry["cost_hint"] == "free, local"


def test_unavailable_and_hidden_candidates(client: TestClient, owner: dict, stub: dict, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_credential(db, owner["user"], status=AiCredentialStatus.ERROR, last_error="Connection refused by the server.")
    _openai_credential(db, owner["user"])
    body = _choices(client, owner)
    by_id = {c["id"]: c for c in body["candidates"]}
    assert by_id[f"openai_compatible:{STUB_MODEL}"]["available"] is False
    assert by_id[f"openai_compatible:{STUB_MODEL}"]["unavailable_reason"] == "Connection refused by the server."
    gpt = by_id["openai:gpt-4o-mini"]
    assert gpt["hosted"] is True and gpt["available"] is False and "hosted" in gpt["unavailable_reason"]
    assert gpt["cost_hint"].startswith("≈ $") and gpt["cost_hint"].endswith("per 1k tokens")
    assert body["usable_count"] == 1 and body["should_ask"] is False

    monkeypatch.setattr(settings, "AI_ALLOW_HOSTED_PROVIDERS", False)
    choice.invalidate_choices()
    hidden = _choices(client, owner)
    assert not any(c["provider"] == "openai" for c in hidden["candidates"])


def test_recent_models_and_last_used(client: TestClient, owner: dict, stub: dict, db: Session) -> None:
    _stub_credential(db, owner["user"])
    when = datetime.now(timezone.utc) - timedelta(hours=2)
    for model in ("stub-old-a", "stub-old-b"):
        db.add(
            AiUsageEvent(
                user_id=owner["user"].id, provider="openai_compatible", model=model, task="tailor_resume", workflow="generation",
                status=AiUsageStatus.OK, created_at=when,
            )
        )
    db.commit()
    body = _choices(client, owner)
    by_id = {c["id"]: c for c in body["candidates"]}
    assert "openai_compatible:stub-old-a" in by_id and "openai_compatible:stub-old-b" in by_id
    assert by_id["openai_compatible:stub-old-a"]["last_used_at"] is not None


def test_choices_are_cached_and_invalidated_by_settings_writes(client: TestClient, owner: dict, stub: dict, db: Session) -> None:
    stub["ollama"] = ["qwen2.5:3b-instruct"]
    first = _choices(client, owner)
    assert first["usable_count"] == 2
    stub["ollama"] = ["qwen2.5:3b-instruct", "llama3.2:1b"]
    assert _choices(client, owner)["usable_count"] == 2  # cached
    r = client.patch(f"{AI}/settings", json={"model_prompt_mode": "default"}, headers=owner["headers"])
    assert r.status_code == 200, r.text
    fresh = _choices(client, owner)
    assert fresh["usable_count"] == 3 and fresh["mode"] == "default" and fresh["should_ask"] is False


def test_ats_polish_belongs_to_the_ats_analysis_workflow(client: TestClient, owner: dict, stub: dict) -> None:
    assert routing.workflow_for("polish_suggestions") == routing.AiWorkflow.ANALYSIS
    assert routing.workflow_for("tailor_resume") == routing.AiWorkflow.GENERATION
    polish = _choices(client, owner, "polish_suggestions")
    assert (polish["workflow"], polish["workflow_label"]) == ("analysis", "ATS analysis")
    tailor = _choices(client, owner, "tailor_resume")
    assert (tailor["workflow"], tailor["workflow_label"]) == ("generation", "Resume generation")


def test_remembered_analysis_model_runs_the_polish(client: TestClient, owner: dict, stub: dict, db: Session) -> None:
    _stub_credential(db, owner["user"])
    r = client.patch(f"{AI}/settings", json={"remember": {"workflow": "analysis", **STUB_CHOICE}}, headers=owner["headers"])
    assert r.status_code == 200, r.text
    assert _choices(client, owner, "polish_suggestions")["default"] == f"openai_compatible:{STUB_MODEL}"
    body = {"resume_id": owner["resume_id"], "jd": {"text": BACKEND_JD, "company": "Acme"}}
    analysis = client.post(f"{ATS}/analyses", json=body, headers=owner["headers"]).json()
    assert analysis["status"] == "RUNNING"  # no pick: the routing for ATS analysis is the stub
    deadline = time.monotonic() + 20
    while analysis["status"] == "RUNNING" and time.monotonic() < deadline:
        time.sleep(0.2)
        analysis = client.get(f"{ATS}/analyses/{analysis['id']}", headers=owner["headers"]).json()
    assert analysis["ai_model"] == STUB_MODEL
    events = _events(db, owner["user"])
    assert events and all((e.task, e.source) == ("polish_suggestions", "task_override") for e in events)


def test_choices_rejects_a_bad_task_name(client: TestClient, owner: dict, stub: dict) -> None:
    r = client.get(f"{AI}/choices", params={"task": "DROP TABLE"}, headers=owner["headers"])
    assert r.status_code == 422


# --------------------------------------------------------------------------- settings


def test_prompt_mode_is_persisted_and_put_keeps_it(client: TestClient, owner: dict, stub: dict, db: Session) -> None:
    h = owner["headers"]
    assert client.get(f"{AI}/settings", headers=h).json()["model_prompt_mode"] == "ask"
    r = client.patch(f"{AI}/settings", json={"model_prompt_mode": "default"}, headers=h)
    assert r.status_code == 200 and r.json()["model_prompt_mode"] == "default"
    db.expire_all()
    row = db.scalar(select(AiProviderSettings).where(AiProviderSettings.user_id == owner["user"].id))
    assert row is not None and row.model_prompt_mode == "default"
    # an older client's full PUT without the field keeps the mode
    r = client.put(f"{AI}/settings", json={"daily_call_limit": 50}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["model_prompt_mode"] == "default" and r.json()["daily_call_limit"] == 50
    r = client.put(f"{AI}/settings", json={"model_prompt_mode": "ask"}, headers=h)
    assert r.json()["model_prompt_mode"] == "ask"
    assert client.patch(f"{AI}/settings", json={"model_prompt_mode": "sometimes"}, headers=h).status_code == 422


def test_remember_sets_the_workflow_model(client: TestClient, owner: dict, stub: dict, db: Session) -> None:
    _stub_credential(db, owner["user"])
    stub["ollama"] = ["qwen2.5:3b-instruct"]
    r = client.patch(
        f"{AI}/settings",
        json={"remember": {"workflow": "analysis", **STUB_CHOICE}},
        headers=owner["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["workflow_models"]["analysis"] == STUB_CHOICE
    assert r.json()["effective"]["analysis"]["provider"] == "openai_compatible"
    body = _choices(client, owner)
    assert body["default"] == f"openai_compatible:{STUB_MODEL}"
    assert body["candidates"][0]["source"] == "workflow_default"
    # other workflows are untouched
    assert _choices(client, owner, "parse_resume")["default"] == MOCK_ID


def test_remember_validates_like_put(client: TestClient, owner: dict, stub: dict, db: Session) -> None:
    _openai_credential(db, owner["user"])
    r = client.patch(
        f"{AI}/settings", json={"remember": {"workflow": "analysis", "provider": "openai", "model": "gpt-4o-mini"}}, headers=owner["headers"]
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "data_residency_ack_required"


# --------------------------------------------------------------------------- validation


def _parse(client: TestClient, owner: dict, ai: dict | None, *, use_ai: bool = True):
    body: dict[str, Any] = {"text": BACKEND_JD, "use_ai": use_ai}
    if ai is not None:
        body["ai"] = ai
    return client.post(f"{ATS}/jd/parse", json=body, headers=owner["headers"])


def test_hosted_disabled_is_403(client: TestClient, owner: dict, stub: dict, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _openai_credential(db, owner["user"])
    monkeypatch.setattr(settings, "AI_ALLOW_HOSTED_PROVIDERS", False)
    r = _parse(client, owner, {"provider": "openai", "model": "gpt-4o-mini"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "ai_hosted_disabled"


def test_missing_credential_is_409(client: TestClient, owner: dict, stub: dict) -> None:
    r = _parse(client, owner, {"provider": "openai", "model": "gpt-4o-mini"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "ai_credential_missing"
    r = _parse(client, owner, STUB_CHOICE)  # an OpenAI-compatible server without its base URL
    assert r.status_code == 409 and r.json()["error"]["code"] == "ai_credential_missing"


def test_unknown_model_is_422(client: TestClient, owner: dict, stub: dict, db: Session) -> None:
    stub["ollama"] = ["qwen2.5:3b-instruct"]
    r = _parse(client, owner, {"provider": "ollama", "model": "not-pulled:7b"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "ai_model_unknown"
    _stub_credential(db, owner["user"])
    r = _parse(client, owner, {"provider": "openai_compatible", "model": "not-on-the-server"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "ai_model_unknown"
    r = _parse(client, owner, {"provider": "gemini-pro", "model": "x"})
    assert r.status_code == 422  # not a provider id at all


def test_hosted_without_acknowledgement_is_422(client: TestClient, owner: dict, stub: dict, db: Session) -> None:
    _openai_credential(db, owner["user"])
    r = _parse(client, owner, {"provider": "openai", "model": "gpt-4o-mini"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "data_residency_ack_required"
    _settings(db, owner["user"], data_residency_ack=True)
    r = _parse(client, owner, {"provider": "openai", "model": "gpt-4o-mini"})
    assert r.status_code == 200, r.text


def test_multipart_choice_fields(client: TestClient, owner: dict, stub: dict, db: Session) -> None:
    files = {"file": ("jd.txt", io.BytesIO(BACKEND_JD.encode()), "text/plain")}
    r = client.post(f"{ATS}/jd/upload", files=files, data={"use_ai": "true", "ai_provider": "ollama"}, headers=owner["headers"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "ai_choice_incomplete"
    _stub_credential(db, owner["user"])
    files = {"file": ("jd.txt", io.BytesIO(BACKEND_JD.encode()), "text/plain")}
    r = client.post(
        f"{ATS}/jd/upload", files=files,
        data={"use_ai": "true", "ai_provider": "openai_compatible", "ai_model": STUB_MODEL}, headers=owner["headers"],
    )
    assert r.status_code == 200, r.text
    assert any(c["provider"] == "openai_compatible" for c in stub["calls"])


# --------------------------------------------------------------------------- the override reaches the runtime


def test_override_reaches_the_runtime_on_jd_parse(client: TestClient, owner: dict, stub: dict, db: Session) -> None:
    _stub_credential(db, owner["user"])
    # mode "default" does not matter: a valid per-run choice is always honoured
    _settings(db, owner["user"], model_prompt_mode="default")
    r = _parse(client, owner, STUB_CHOICE)
    assert r.status_code == 200, r.text
    assert [c["provider"] for c in stub["calls"]] == ["openai_compatible"]
    assert stub["calls"][0]["model"] == STUB_MODEL
    events = _events(db, owner["user"])
    assert len(events) == 1
    assert (events[0].provider, events[0].model, events[0].source, events[0].task) == (
        "openai_compatible", STUB_MODEL, "per_run", "analyze_job_description"
    )
    # without a choice the routing (the mock server default) applies: no model call at all
    stub["calls"].clear()
    assert _parse(client, owner, None).status_code == 200
    assert stub["calls"] == []


def test_override_reaches_the_background_polish_of_an_analysis(client: TestClient, owner: dict, stub: dict, db: Session) -> None:
    _stub_credential(db, owner["user"])
    body = {"resume_id": owner["resume_id"], "jd": {"text": BACKEND_JD, "company": "Acme"}, "ai": STUB_CHOICE}
    r = client.post(f"{ATS}/analyses", json=body, headers=owner["headers"])
    assert r.status_code == 201, r.text
    analysis = r.json()
    assert analysis["status"] == "RUNNING"  # a model was picked, so the suggestions get polished
    deadline = time.monotonic() + 20
    while analysis["status"] == "RUNNING" and time.monotonic() < deadline:
        time.sleep(0.2)
        analysis = client.get(f"{ATS}/analyses/{analysis['id']}", headers=owner["headers"]).json()
    assert analysis["status"] == "DONE", analysis
    assert (analysis["ai_provider"], analysis["ai_model"]) == ("openai_compatible", STUB_MODEL)
    assert stub["calls"] and all(c["provider"] == "openai_compatible" and c["model"] == STUB_MODEL for c in stub["calls"])
    events = _events(db, owner["user"])
    assert events and all(e.source == "per_run" and e.provider == "openai_compatible" for e in events)
    assert {(e.task, e.workflow) for e in events} == {("polish_suggestions", "analysis")}
    db.expire_all()
    row = db.get(AtsAnalysis, uuid.UUID(analysis["id"]))
    assert row is not None and row.ai_model == STUB_MODEL


def test_override_on_retry_polish_and_writing_help(client: TestClient, owner: dict, stub: dict, db: Session) -> None:
    _stub_credential(db, owner["user"])
    created = client.post(
        f"{ATS}/analyses", json={"resume_id": owner["resume_id"], "jd": {"text": BACKEND_JD}}, headers=owner["headers"]
    ).json()
    assert created["status"] == "DONE"  # mock routing: nothing to polish
    r = client.post(f"{ATS}/analyses/{created['id']}/polish", json={"ai": STUB_CHOICE}, headers=owner["headers"])
    assert r.status_code == 200, r.text
    r = client.post(
        f"/api/v1/resumes/{owner['resume_id']}/ai/improve-text",
        json={"text": "i build api for payment team", "field": "summary", "ai": STUB_CHOICE},
        headers=owner["headers"],
    )
    assert r.status_code == 200, r.text
    assert any(c["provider"] == "openai_compatible" and c["model"] == STUB_MODEL for c in stub["calls"])
    body = r.json()
    if body["source"] == "ai":  # the stub's answer may be refused by the guards (then only rules ran)
        assert (body["ai_provider"], body["ai_model"]) == ("openai_compatible", STUB_MODEL)
    else:
        assert body["ai_provider"] is None


def test_runtime_unit_override_and_last_call(db: Session, owner: dict, stub: dict) -> None:
    _stub_credential(db, owner["user"])
    target = routing.Target("openai_compatible", STUB_MODEL)
    with context.ai_user(owner["user"].id, target_override=target):
        resolved = runtime.resolve_current("analyze_resume_fit")
        assert (resolved.provider, resolved.model, resolved.source) == ("openai_compatible", STUB_MODEL, "per_run")
        runtime.complete_json("analyze_resume_fit", "hello", schema={"type": "object"})
        info = runtime.last_call()
        assert info is not None and (info.provider, info.model, info.source) == ("openai_compatible", STUB_MODEL, "per_run")
        # another user's resolution never sees this user's choice
        other = runtime.resolve_current("analyze_resume_fit", user_id=uuid.uuid4())
        assert other.source != "per_run"
    with context.ai_user(owner["user"].id):
        assert runtime.resolve_current("analyze_resume_fit").source == "server_default"


def test_fallback_still_applies_after_the_chosen_model_fails(db: Session, owner: dict, stub: dict) -> None:
    _stub_credential(db, owner["user"])
    _settings(db, owner["user"], fallback_enabled=True, fallback_provider="ollama", fallback_model="qwen2.5:3b-instruct")
    stub["fail"].add(("openai_compatible", STUB_MODEL))
    target = routing.Target("openai_compatible", STUB_MODEL)
    with context.ai_user(owner["user"].id, target_override=target):
        runtime.complete_json("tailor_resume", "hello", schema={"type": "object"})
        info = runtime.last_call()
    assert info is not None and info.fallback_used is True and info.provider == "ollama"
    assert info.primary == {"provider": "openai_compatible", "model": STUB_MODEL}
    events = _events(db, owner["user"])
    assert [(e.provider, e.status.value, e.source) for e in events] == [
        ("openai_compatible", "ERROR", "per_run"),
        ("ollama", "FALLBACK", "fallback"),
    ]


def test_limits_apply_to_the_chosen_provider(db: Session, owner: dict, stub: dict) -> None:
    _stub_credential(db, owner["user"])
    _settings(db, owner["user"], daily_call_limit=1)
    target = routing.Target("openai_compatible", STUB_MODEL)
    with context.ai_user(owner["user"].id, target_override=target):
        runtime.complete_json("tailor_resume", "one", schema={"type": "object"})
        with pytest.raises(AIProviderError) as err:
            runtime.complete_json("tailor_resume", "two", schema={"type": "object"})
    assert err.value.code == "budget_exceeded"
