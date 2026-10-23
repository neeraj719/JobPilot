"""ai-providers runtime: context, routing, fallback, limits, usage, error mapping, tasks.

No network: providers are fakes injected through ``runtime.construct_provider``.
"""
from __future__ import annotations

import threading
import uuid
from decimal import Decimal
from typing import Any

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ExternalServiceError
from app.core.security import create_access_token, encrypt_str, hash_password
from app.models.ai_settings import AiProviderCredential, AiProviderSettings, AiUsageEvent
from app.models.user import User
from app.modules.ai import context, routing, runtime, tasks
from app.modules.ai.errors import AIProviderError, map_exception
from app.modules.ai.provider import LLMProvider, report_usage
from app.modules.ai.providers.mock import MockLLMProvider
from app.modules.ai.safety import UNTRUSTED_RULES
from app.modules.ai.schemas import EmailClassificationResult


# --------------------------------------------------------------------------- fakes


class FakeProvider(LLMProvider):
    def __init__(self, name: str, model: str, *, reply: Any = None, error: Exception | None = None, usage: tuple[int, int] | None = (120, 30)) -> None:
        self.name = name
        self.model = model
        self.reply = reply if reply is not None else {"ok": True}
        self.error = error
        self.usage = usage
        self.calls: list[dict[str, Any]] = []

    def _go(self, prompt: str, system: str | None) -> Any:
        self.calls.append({"prompt": prompt, "system": system})
        if self.error is not None:
            raise self.error
        if self.usage:
            report_usage(*self.usage)
        return self.reply

    def complete(self, prompt, *, system=None, max_tokens=800, temperature=0.2):  # noqa: ANN001, ANN201
        out = self._go(prompt, system)
        return out if isinstance(out, str) else "text answer"

    def complete_json(self, prompt, *, schema=None, system=None, max_tokens=1500):  # noqa: ANN001, ANN201
        return self._go(prompt, system)


class Factory:
    """Stands in for ``runtime.construct_provider``; records which keys built which client."""

    def __init__(self) -> None:
        self.providers: dict[tuple[str, str], FakeProvider] = {}
        self.built: list[dict[str, Any]] = []

    def set(self, name: str, model: str, **kw: Any) -> FakeProvider:
        provider = FakeProvider(name, model, **kw)
        self.providers[(name, model)] = provider
        return provider

    def __call__(self, provider: str, model: str, *, api_key: str | None = None, base_url: str | None = None) -> LLMProvider:
        self.built.append({"provider": provider, "model": model, "api_key": api_key, "base_url": base_url})
        if provider == "mock":
            return MockLLMProvider()
        try:
            return self.providers[(provider, model)]
        except KeyError:
            raise AIProviderError("model_unavailable", f"no fake for {provider}/{model}", provider=provider, model=model) from None


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> Factory:
    factory = Factory()
    monkeypatch.setattr(runtime, "construct_provider", factory)
    runtime.clear_client_cache()
    yield factory
    runtime.clear_client_cache()


@pytest.fixture
def user(db: Session) -> User:
    row = User(email=f"rt-{uuid.uuid4().hex[:8]}@example.com", hashed_password=hash_password("StrongPass123!"), full_name="Runtime", is_active=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _settings(db: Session, user: User, **fields: Any) -> AiProviderSettings:
    row = AiProviderSettings(user_id=user.id, workflow_models=fields.pop("workflow_models", {}), **fields)
    db.add(row)
    db.commit()
    return row


def _credential(db: Session, user: User, provider: str, key: str = "sk-test-key-1234", **fields: Any) -> AiProviderCredential:
    row = AiProviderCredential(user_id=user.id, provider=provider, encrypted_api_key=encrypt_str(key), key_hint=key[-4:], credential_version=1, **fields)
    db.add(row)
    db.commit()
    return row


def _events(db: Session, user: User) -> list[AiUsageEvent]:
    db.expire_all()
    return list(db.scalars(select(AiUsageEvent).where(AiUsageEvent.user_id == user.id).order_by(AiUsageEvent.created_at)))


# --------------------------------------------------------------------------- context


def test_ai_user_sets_and_resets_the_current_user() -> None:
    uid = uuid.uuid4()
    assert context.current_ai_user() is None
    with context.ai_user(uid):
        assert context.current_ai_user() == uid
        inner = uuid.uuid4()
        with context.ai_user(inner):
            assert context.current_ai_user() == inner
        assert context.current_ai_user() == uid
    assert context.current_ai_user() is None


def test_ai_user_is_per_thread() -> None:
    seen: dict[str, Any] = {}
    a, b = uuid.uuid4(), uuid.uuid4()
    barrier = threading.Barrier(2)

    def work(name: str, uid: uuid.UUID) -> None:
        with context.ai_user(uid):
            barrier.wait()
            seen[name] = context.current_ai_user()

    threads = [threading.Thread(target=work, args=("a", a)), threading.Thread(target=work, args=("b", b))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert seen == {"a": a, "b": b}
    assert context.current_ai_user() is None


def test_request_user_is_published_and_does_not_leak_between_requests(client: TestClient, db: Session) -> None:
    from app.core.deps import get_current_user
    from app.main import app

    def probe(user: User = Depends(get_current_user)) -> dict[str, Any]:
        slot = context._slot.get()
        return {"slot": str(slot.user_id) if slot and slot.user_id else None, "user": str(user.id)}

    app.add_api_route("/__test/ai-user", probe, methods=["GET"])
    try:
        users = []
        for i in range(2):
            u = User(email=f"ctx{i}@example.com", hashed_password=hash_password("StrongPass123!"), full_name="Ctx", is_active=True)
            db.add(u)
            db.commit()
            users.append(u)
        for _ in range(2):
            for u in users:
                token = create_access_token(u.id, u.role.value)
                body = client.get("/__test/ai-user", headers={"Authorization": f"Bearer {token}"}).json()
                assert body == {"slot": str(u.id), "user": str(u.id)}
        assert client.get("/__test/ai-user").status_code == 401
        assert context.current_ai_user() is None  # nothing leaked into the test thread
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != "/__test/ai-user"]


# --------------------------------------------------------------------------- routing


def test_every_existing_and_contract_task_is_mapped() -> None:
    for task in ("parse_resume", "polish_resume_recommendations", "explain_match", "generate_answer",
                 "generate_cover_letter", "classify_email", "generate_interview_prep"):
        assert task in routing.TASK_WORKFLOWS
    assert routing.workflow_for("rewrite_bullet") == routing.AiWorkflow.REWRITING
    assert routing.workflow_for("analyze_job_description") == routing.AiWorkflow.JD_ANALYSIS
    assert routing.workflow_for("analyze_resume_fit") == routing.AiWorkflow.ANALYSIS
    assert routing.workflow_for("tailor_resume") == routing.AiWorkflow.GENERATION
    assert routing.workflow_for("review_resume") == routing.AiWorkflow.REVIEW
    assert routing.workflow_for("something_new") == routing.AiWorkflow.GENERAL


def test_resolution_precedence_task_override_then_user_default_then_server_default(db: Session, user: User) -> None:
    assert routing.resolve(db, user.id, "rewrite_bullet").source == "server_default"
    assert routing.resolve(db, None, "rewrite_bullet").provider == "mock"

    _settings(db, user, default_provider="openai", default_model="gpt-4o-mini",
              workflow_models={"rewriting": {"provider": "anthropic", "model": "claude-haiku-5-5"}})
    rewrite = routing.resolve(db, user.id, "rewrite_bullet")
    assert (rewrite.provider, rewrite.model, rewrite.source) == ("anthropic", "claude-haiku-5-5", "task_override")
    other = routing.resolve(db, user.id, "analyze_resume_fit")
    assert (other.provider, other.model, other.source) == ("openai", "gpt-4o-mini", "user_default")
    assert other.fallback is None


def test_fallback_is_only_resolved_when_enabled_and_different(db: Session, user: User) -> None:
    row = _settings(db, user, default_provider="openai", default_model="gpt-4o-mini",
                    fallback_provider="ollama", fallback_model="qwen2.5:3b-instruct", fallback_enabled=False)
    assert routing.resolve(db, user.id, "general").fallback is None
    row.fallback_enabled = True
    db.commit()
    assert routing.resolve(db, user.id, "general").fallback == routing.Target("ollama", "qwen2.5:3b-instruct")
    row.fallback_provider, row.fallback_model = "openai", "gpt-4o-mini"
    db.commit()
    assert routing.resolve(db, user.id, "general").fallback is None  # same as the primary


# --------------------------------------------------------------------------- calls


def test_complete_json_uses_the_users_provider_records_usage_and_prepends_rules(db: Session, user: User, fakes: Factory) -> None:
    _credential(db, user, "openai", key="sk-live-secret-9876")
    _settings(db, user, default_provider="openai", default_model="gpt-4o-mini", data_residency_ack=True)
    fake = fakes.set("openai", "gpt-4o-mini", reply={"answer": 42}, usage=(1000, 500))

    with context.ai_user(user.id):
        data = runtime.complete_json("analyze_resume_fit", "Prompt", schema={"type": "object"}, system="Task rules.")
        info = runtime.last_call()

    assert data == {"answer": 42}
    assert fake.calls[0]["system"].startswith(UNTRUSTED_RULES) and fake.calls[0]["system"].endswith("Task rules.")
    assert fakes.built[-1]["api_key"] == "sk-live-secret-9876"  # decrypted only to build the client
    [event] = _events(db, user)
    assert (event.provider, event.model, event.task, event.workflow) == ("openai", "gpt-4o-mini", "analyze_resume_fit", "analysis")
    assert (event.input_tokens, event.output_tokens, event.tokens_estimated) == (1000, 500, False)
    assert str(event.status) == "OK" and event.duration_ms >= 0
    assert event.estimated_cost_usd == Decimal("0.000450")  # 1000*0.15/1M + 500*0.60/1M
    assert info.provider == "openai" and info.fallback_used is False and info.estimated_cost_usd == pytest.approx(0.00045)


def test_tokens_are_estimated_and_flagged_when_the_sdk_reports_none(db: Session, user: User, fakes: Factory) -> None:
    _settings(db, user, default_provider="ollama", default_model="qwen2.5:3b-instruct")
    fakes.set("ollama", "qwen2.5:3b-instruct", reply="x" * 400, usage=None)
    with context.ai_user(user.id):
        assert runtime.complete("draft_summary", "y" * 4000) == "x" * 400
    [event] = _events(db, user)
    assert event.tokens_estimated is True and event.input_tokens >= 1000 and event.output_tokens == 100
    assert event.estimated_cost_usd == Decimal("0")  # local models are free


def test_clients_are_cached_per_credential_version_and_never_shared(db: Session, user: User, fakes: Factory) -> None:
    cred = _credential(db, user, "openai")
    _settings(db, user, default_provider="openai", default_model="gpt-4o-mini", data_residency_ack=True)
    fakes.set("openai", "gpt-4o-mini")
    with context.ai_user(user.id):
        runtime.complete_json("general", "a", schema=None)
        runtime.complete_json("general", "b", schema=None)
    assert len(fakes.built) == 1
    keys = runtime.cached_client_keys()
    assert keys and all("sk-" not in repr(k) for k in keys)  # no secret in a cache key

    cred.credential_version = 2
    db.commit()
    with context.ai_user(user.id):
        runtime.complete_json("general", "c", schema=None)
    assert len(fakes.built) == 2  # rotation means a new client

    other = User(email="other-cache@example.com", hashed_password=hash_password("StrongPass123!"), full_name="O", is_active=True)
    db.add(other)
    db.commit()
    with context.ai_user(other.id):  # no settings, no key: server default (mock)
        assert runtime.resolve_current("general").provider == "mock"


def test_missing_key_is_provider_not_configured(db: Session, user: User, fakes: Factory) -> None:
    _settings(db, user, default_provider="anthropic", default_model="claude-haiku-5-5", data_residency_ack=True)
    with context.ai_user(user.id), pytest.raises(AIProviderError) as err:
        runtime.complete_json("general", "x", schema=None)
    assert err.value.code == "provider_not_configured"
    assert isinstance(err.value, ExternalServiceError)


def test_fallback_runs_only_when_enabled_and_is_recorded(db: Session, user: User, fakes: Factory) -> None:
    _credential(db, user, "openai")
    row = _settings(db, user, default_provider="openai", default_model="gpt-4o-mini", data_residency_ack=True,
                    fallback_provider="ollama", fallback_model="qwen2.5:3b-instruct", fallback_enabled=False)
    fakes.set("openai", "gpt-4o-mini", error=TimeoutError("read timed out"))
    backup = fakes.set("ollama", "qwen2.5:3b-instruct", reply={"from": "fallback"})

    with context.ai_user(user.id), pytest.raises(AIProviderError) as err:
        runtime.complete_json("general", "x", schema=None)
    assert err.value.code == "provider_timeout"
    assert backup.calls == []  # disabled: never used

    row.fallback_enabled = True
    db.commit()
    with context.ai_user(user.id):
        assert runtime.complete_json("general", "x", schema=None) == {"from": "fallback"}
        info = runtime.last_call()
    assert info.fallback_used and info.provider == "ollama" and info.primary == {"provider": "openai", "model": "gpt-4o-mini"}
    assert info.primary_error_code == "provider_timeout"
    statuses = [(e.provider, str(e.status), e.error_code) for e in _events(db, user)]
    assert statuses[-2:] == [("openai", "ERROR", "provider_timeout"), ("ollama", "FALLBACK", None)]


def test_daily_call_limit_is_enforced_before_the_call(db: Session, user: User, fakes: Factory) -> None:
    _credential(db, user, "openai")
    _settings(db, user, default_provider="openai", default_model="gpt-4o-mini", data_residency_ack=True, daily_call_limit=2,
              fallback_provider="ollama", fallback_model="qwen2.5:3b-instruct", fallback_enabled=True)
    fake = fakes.set("openai", "gpt-4o-mini")
    backup = fakes.set("ollama", "qwen2.5:3b-instruct")
    with context.ai_user(user.id):
        runtime.complete_json("general", "1", schema=None)
        runtime.complete_json("general", "2", schema=None)
        with pytest.raises(AIProviderError) as err:
            runtime.complete_json("general", "3", schema=None)
    assert err.value.code == "budget_exceeded" and err.value.status_code == 429
    assert len(fake.calls) == 2 and backup.calls == []  # no request made, and no fallback for a budget stop


def test_monthly_budget_is_enforced(db: Session, user: User, fakes: Factory) -> None:
    _credential(db, user, "openai")
    _settings(db, user, default_provider="openai", default_model="gpt-4o", data_residency_ack=True, monthly_budget_usd=Decimal("0.01"))
    fakes.set("openai", "gpt-4o", usage=(2000, 1000))  # 0.005 + 0.01 = 0.015 USD
    with context.ai_user(user.id):
        runtime.complete_json("general", "1", schema=None)
        with pytest.raises(AIProviderError) as err:
            runtime.complete_json("general", "2", schema=None)
    assert err.value.code == "budget_exceeded"
    assert err.value.details["limit"] == "monthly_budget"


@pytest.mark.parametrize(
    ("exc_name", "status", "message", "code"),
    [
        ("AuthenticationError", 401, "Incorrect API key provided: sk-abc***xyz", "invalid_credentials"),
        ("PermissionDeniedError", 403, "denied", "invalid_credentials"),
        ("RateLimitError", 429, "You exceeded your current quota", "quota_exceeded"),
        ("NotFoundError", 404, "The model `gpt-9` does not exist", "model_unavailable"),
        ("APITimeoutError", None, "Request timed out.", "provider_timeout"),
        ("InternalServerError", 500, "boom", "provider_error"),
        ("BadRequestError", 400, "Your credit balance is too low", "quota_exceeded"),
        ("ClientError", 400, "API key not valid. Please pass a valid API key.", "invalid_credentials"),
        ("APIConnectionError", None, "Connection error.", "provider_error"),
    ],
)
def test_error_mapping(exc_name: str, status: int | None, message: str, code: str) -> None:
    cls = type(exc_name, (Exception,), {})
    exc = cls(message)
    if status is not None:
        exc.status_code = status
    err = map_exception("openai", exc, model="gpt-4o-mini")
    assert err.code == code
    assert "sk-abc" not in err.message and message not in err.message  # never the raw body


def test_real_sdk_exceptions_map_too() -> None:
    import httpx
    import openai

    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(401, request=request, json={"error": {"message": "Incorrect API key provided: sk-proj-XXXX"}})
    err = map_exception("openai", openai.AuthenticationError("Incorrect API key provided: sk-proj-XXXX", response=response, body=None))
    assert err.code == "invalid_credentials" and "sk-proj" not in err.message
    assert map_exception("openai", openai.APITimeoutError(request=request)).code == "provider_timeout"


def test_legacy_ollama_codes_keep_their_local_message() -> None:
    err = map_exception("ollama", ExternalServiceError("Ollama model 'x' is not pulled. Run: ollama pull x", code="llm_model_missing"))
    assert err.code == "model_unavailable" and "ollama pull" in err.message


def test_usage_failure_never_breaks_the_call(db: Session, user: User, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeProvider("ollama", "qwen2.5:3b-instruct", reply={"fine": True})
    resolved = routing.Resolved("ollama", "qwen2.5:3b-instruct", "user_default", "general", "general", user.id)

    def broken_session():  # noqa: ANN202
        raise RuntimeError("database is down")

    monkeypatch.setattr(runtime, "_session", broken_session)
    data = runtime.complete_json("general", "x", schema=None, prepared=runtime.Prepared(resolved, fake))
    assert data == {"fine": True}


# --------------------------------------------------------------------------- tasks go through the runtime


def test_tasks_short_circuit_to_the_mock_without_touching_providers(fakes: Factory) -> None:
    result = tasks.classify_email("Offer letter", "hr@acme.com", "We are pleased to offer you the role.")
    assert result.classification.value == "OFFER"
    assert fakes.built == []


def test_tasks_honour_the_users_provider(db: Session, user: User, fakes: Factory) -> None:
    _settings(db, user, default_provider="ollama", default_model="qwen2.5:3b-instruct")
    fake = fakes.set("ollama", "qwen2.5:3b-instruct",
                     reply={"classification": "INTERVIEW", "confidence": 0.9, "reason": "invite", "company_name": None, "job_title": None})
    with context.ai_user(user.id):
        result = tasks.classify_email("Interview", "hr@acme.com", "Let's schedule a call.")
    assert isinstance(result, EmailClassificationResult) and result.classification.value == "INTERVIEW"
    assert fake.calls and fake.calls[0]["system"].startswith(UNTRUSTED_RULES)
    [event] = _events(db, user)
    assert event.task == "classify_email" and event.workflow == "general"


def test_tasks_fall_back_to_rules_when_the_users_provider_fails(db: Session, user: User, fakes: Factory) -> None:
    _credential(db, user, "openai")
    _settings(db, user, default_provider="openai", default_model="gpt-4o-mini", data_residency_ack=True)
    fakes.set("openai", "gpt-4o-mini", error=type("AuthenticationError", (Exception,), {"status_code": 401})("bad key"))
    with context.ai_user(user.id):
        result = tasks.classify_email("Offer letter", "hr@acme.com", "We are pleased to offer you the role.")
    assert result.classification.value == "OFFER"  # the deterministic rules answered
    [event] = _events(db, user)
    assert str(event.status) == "ERROR" and event.error_code == "invalid_credentials"


def test_parse_resume_uses_rules_only_when_the_user_routes_to_the_mock(db: Session, user: User, fakes: Factory) -> None:
    _settings(db, user, default_provider="mock", default_model="mock-deterministic-v1")
    with context.ai_user(user.id):
        parsed = tasks.parse_resume("Jane Doe\njane@example.com\nSkills: Python, Django, PostgreSQL")
    assert parsed.email == "jane@example.com"
    assert _events(db, user) == []
