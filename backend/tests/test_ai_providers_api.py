"""AI Model Settings API: credentials (encrypted, masked, never returned), recent auth,
rotation, deletion, settings validation, ownership, tests, model lists and usage."""
from __future__ import annotations

import json
import time
import uuid
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, decrypt_str, hash_password
from app.models.ai_settings import AiProviderCredential, AiUsageEvent
from app.models.audit import AuditLog
from app.models.user import User
from app.modules.ai import base_url as base_url_mod
from app.modules.ai import runtime, settings_service
from app.modules.ai.provider import LLMProvider

SECRET = "sk-proj-SuperSecretValue-ABCD1234wxyz"
OTHER_SECRET = "sk-proj-AnotherSecretValue-ZZZZ9876"
API = "/api/v1/ai"


class StubProvider(LLMProvider):
    """What ``runtime.construct_provider`` returns in these tests (no network)."""

    def __init__(self, name: str, model: str, api_key: str | None, *, fail: str | None = None, models: list[str] | None = None) -> None:
        self.name, self.model, self.api_key, self.fail = name, model, api_key, fail
        self._models = models

    def complete(self, prompt, *, system=None, max_tokens=800, temperature=0.2):  # noqa: ANN001, ANN201
        return "ok"

    def complete_json(self, prompt, *, schema=None, system=None, max_tokens=1500):  # noqa: ANN001, ANN201
        return {"ok": True}

    def list_models(self) -> list[dict[str, Any]] | None:
        if self.fail == "auth":
            err = type("AuthenticationError", (Exception,), {"status_code": 401})(f"Incorrect API key provided: {self.api_key}")
            raise err
        return [{"id": m} for m in (self._models or ["gpt-4o-mini", "gpt-4.1", "gpt-9-preview"])]


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"built": [], "fail": None, "models": None}

    def construct(provider: str, model: str, *, api_key: str | None = None, base_url: str | None = None) -> LLMProvider:
        state["built"].append({"provider": provider, "model": model, "api_key": api_key, "base_url": base_url})
        fail = "auth" if api_key and "bad" in api_key else state["fail"]
        return StubProvider(provider, model, api_key, fail=fail, models=state["models"])

    monkeypatch.setattr(runtime, "construct_provider", construct)
    base_url_mod.set_resolver(lambda host: ["127.0.0.1"] if host in ("localhost", "lmstudio.local") else ["93.184.215.14"])
    runtime.clear_client_cache()
    settings_service._model_cache.clear()
    yield state
    base_url_mod.set_resolver(None)
    runtime.clear_client_cache()
    settings_service._model_cache.clear()


def _user(db: Session, email: str) -> User:
    row = User(email=email, hashed_password=hash_password("StrongPass123!"), full_name="Prov", is_active=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _auth(user: User, *, age_seconds: int = 0) -> dict[str, str]:
    extra = {"iat": int(time.time()) - age_seconds} if age_seconds else None
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value, extra=extra)}"}


@pytest.fixture
def alice(db: Session) -> User:
    return _user(db, "alice-ai@example.com")


@pytest.fixture
def bob(db: Session) -> User:
    return _user(db, "bob-ai@example.com")


def _no_secret(*bodies: Any) -> None:
    for body in bodies:
        text = body if isinstance(body, str) else json.dumps(body)
        for secret in (SECRET, OTHER_SECRET, SECRET[:-4], "SuperSecretValue"):
            assert secret not in text


def _all_reads(client: TestClient, headers: dict[str, str]) -> list[str]:
    paths = ["/providers", "/settings", "/status", "/usage?range=30d", "/providers/openai/models", "/providers/openai/models?live=false"]
    return [client.get(API + p, headers=headers).text for p in paths]


# --------------------------------------------------------------------------- credentials


def test_saving_a_key_encrypts_it_and_never_returns_it(client: TestClient, db: Session, alice: User, stub: dict) -> None:
    h = _auth(alice)
    r = client.put(f"{API}/credentials/openai", json={"api_key": SECRET}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["masked_key"] == "••••wxyz" and body["has_key"] is True and body["status"] == "UNTESTED"
    assert body["credential_version"] == 1
    _no_secret(r.text)

    row = db.scalar(select(AiProviderCredential).where(AiProviderCredential.user_id == alice.id))
    assert row.encrypted_api_key and SECRET not in row.encrypted_api_key
    assert decrypt_str(row.encrypted_api_key) == SECRET  # round trip
    assert row.key_hint == "wxyz"

    test = client.post(f"{API}/credentials/openai/test", json={}, headers=h)
    assert test.status_code == 200 and test.json()["ok"] is True
    _no_secret(test.text, *_all_reads(client, h))

    audits = db.scalars(select(AuditLog).where(AuditLog.user_id == alice.id)).all()
    assert {"ai.credential_saved", "ai.credential_tested"} <= {a.action for a in audits}
    _no_secret([a.message for a in audits], [a.meta for a in audits])


def test_credential_writes_require_recent_auth(client: TestClient, alice: User, stub: dict) -> None:
    stale = _auth(alice, age_seconds=3600)
    r = client.put(f"{API}/credentials/openai", json={"api_key": SECRET}, headers=stale)
    assert r.status_code == 401 and r.json()["error"]["code"] == "reauth_required"
    r = client.put(f"{API}/credentials/openai", json={"api_key": SECRET}, headers={**stale, "X-Reauth-Password": "StrongPass123!"})
    assert r.status_code == 200
    assert client.delete(f"{API}/credentials/openai", headers=stale).status_code == 401
    # reading and testing do not need a fresh sign-in
    assert client.post(f"{API}/credentials/openai/test", headers=stale).status_code == 200


def test_rotation_bumps_the_version_and_evicts_the_cached_client(client: TestClient, db: Session, alice: User, stub: dict) -> None:
    h = _auth(alice)
    client.put(f"{API}/credentials/openai", json={"api_key": SECRET}, headers=h)
    r = client.put(f"{API}/settings", json={"default_provider": "openai", "default_model": "gpt-4o-mini", "data_residency_ack": True}, headers=h)
    assert r.status_code == 200, r.text
    from app.modules.ai.context import ai_user

    with ai_user(alice.id):
        runtime.complete_json("general", "hello", schema=None)
    assert any(k[0] == alice.id for k in runtime.cached_client_keys())
    first_key = stub["built"][-1]["api_key"]

    r = client.put(f"{API}/credentials/openai", json={"api_key": OTHER_SECRET}, headers=h)
    assert r.json()["credential_version"] == 2 and r.json()["rotated_at"] and r.json()["masked_key"] == "••••9876"
    assert not any(k[0] == alice.id for k in runtime.cached_client_keys())
    with ai_user(alice.id):
        runtime.complete_json("general", "hello", schema=None)
    assert first_key == SECRET and stub["built"][-1]["api_key"] == OTHER_SECRET
    assert "ai.credential_rotated" in {a.action for a in db.scalars(select(AuditLog).where(AuditLog.user_id == alice.id))}


def test_delete_wipes_the_ciphertext_and_allows_adding_again(client: TestClient, db: Session, alice: User, stub: dict) -> None:
    h = _auth(alice)
    client.put(f"{API}/credentials/openai", json={"api_key": SECRET}, headers=h)
    assert client.delete(f"{API}/credentials/openai", headers=h).status_code == 204
    rows = db.scalars(
        select(AiProviderCredential).where(AiProviderCredential.user_id == alice.id).execution_options(include_deleted=True)
    ).all()
    assert len(rows) == 1 and rows[0].deleted_at is not None
    assert rows[0].encrypted_api_key is None and rows[0].key_hint is None
    assert client.delete(f"{API}/credentials/openai", headers=h).status_code == 404
    assert client.put(f"{API}/credentials/openai", json={"api_key": OTHER_SECRET}, headers=h).json()["credential_version"] == 1


def test_an_invalid_key_reports_an_actionable_error(client: TestClient, alice: User, stub: dict) -> None:
    h = _auth(alice)
    bad = "sk-bad-key-0000-fake"
    client.put(f"{API}/credentials/openai", json={"api_key": bad}, headers=h)
    r = client.post(f"{API}/credentials/openai/test", json={}, headers=h)
    body = r.json()
    assert r.status_code == 200 and body["ok"] is False and body["error_code"] == "invalid_credentials"
    assert "rejected the API key" in body["error"] and "subscription" in body["error"]
    assert bad not in r.text and bad not in client.get(f"{API}/providers", headers=h).text
    cred = next(p for p in client.get(f"{API}/providers", headers=h).json()["providers"] if p["id"] == "openai")["credential"]
    assert cred["status"] == "ERROR" and cred["last_error_code"] == "invalid_credentials"


def test_credential_validation(client: TestClient, alice: User, stub: dict) -> None:
    h = _auth(alice)
    assert client.put(f"{API}/credentials/openai", json={}, headers=h).json()["error"]["code"] == "api_key_required"
    assert client.put(f"{API}/credentials/openai", json={"api_key": "short"}, headers=h).status_code == 422
    assert client.put(f"{API}/credentials/openai", json={"api_key": "has space inside key"}, headers=h).status_code == 422
    assert client.put(f"{API}/credentials/ollama", json={"api_key": SECRET, "base_url": "http://localhost:11434"}, headers=h).status_code == 422
    assert client.put(f"{API}/credentials/openai", json={"api_key": SECRET, "base_url": "https://x.example"}, headers=h).status_code == 422
    assert client.put(f"{API}/credentials/mock", json={}, headers=h).status_code == 404
    assert client.put(f"{API}/credentials/nope", json={}, headers=h).status_code == 404


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        ("http://localhost:1234/v1", True),
        ("https://api.example.com/v1", True),
        ("http://api.example.com/v1", False),  # plain http only for local servers
        ("http://169.254.169.254/latest", False),  # cloud metadata
        ("http://metadata.google.internal/", False),
        ("ftp://localhost/", False),
        ("http://user:pw@localhost:1234/v1", False),
        ("http://[::ffff:169.254.169.254]/", False),
        ("http://0.0.0.0:8000", False),
    ],
)
def test_openai_compatible_base_url_validation(client: TestClient, alice: User, stub: dict, url: str, ok: bool) -> None:
    r = client.put(f"{API}/credentials/openai_compatible", json={"base_url": url}, headers=_auth(alice))
    assert (r.status_code == 200) is ok, r.text
    if not ok:
        assert r.json()["error"]["code"] in ("invalid_base_url", "validation_error")


def test_local_base_urls_can_be_disabled(client: TestClient, alice: User, stub: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "AI_ALLOW_LOCAL_BASE_URLS", False)
    r = client.put(f"{API}/credentials/openai_compatible", json={"base_url": "http://localhost:1234/v1"}, headers=_auth(alice))
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_base_url"


# --------------------------------------------------------------------------- settings


def test_settings_defaults_to_the_server_model(client: TestClient, alice: User, stub: dict) -> None:
    body = client.get(f"{API}/settings", headers=_auth(alice)).json()
    assert body["default_provider"] is None and body["fallback_enabled"] is False
    assert body["effective"]["generation"] == {"provider": "mock", "model": "mock-deterministic-v1", "source": "server_default", "usable": True, "problem": None}
    assert body["status"]["configured"] is True
    assert body["summary"].startswith("Built-in rules")


def test_settings_validation(client: TestClient, alice: User, stub: dict) -> None:
    h = _auth(alice)
    put = lambda payload: client.put(f"{API}/settings", json=payload, headers=h)  # noqa: E731
    assert put({"default_provider": "openai", "default_model": "gpt-4o-mini"}).json()["error"]["code"] == "provider_not_configured"
    client.put(f"{API}/credentials/openai", json={"api_key": SECRET}, headers=h)
    assert put({"default_provider": "openai", "default_model": "gpt-4o-mini"}).json()["error"]["code"] == "data_residency_ack_required"
    r = put({"default_provider": "openai", "default_model": "gpt-does-not-exist", "data_residency_ack": True})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_model"
    assert put({"default_provider": "martian"}).status_code == 422
    assert put({"workflow_models": {"teleport": {"provider": "mock", "model": "x"}}}).status_code == 422
    assert put({"fallback_enabled": True}).json()["error"]["code"] == "fallback_required"
    assert put({"daily_call_limit": 0}).status_code == 422
    assert put({"monthly_budget_usd": -1}).status_code == 422

    # a live-listed model that is not in the registry is allowed (pricing unknown)
    r = put({"default_provider": "openai", "default_model": "gpt-9-preview", "data_residency_ack": True})
    assert r.status_code == 200, r.text


def test_settings_round_trip_with_overrides_fallback_and_limits(client: TestClient, db: Session, alice: User, stub: dict) -> None:
    h = _auth(alice)
    client.put(f"{API}/credentials/openai", json={"api_key": SECRET}, headers=h)
    payload = {
        "default_provider": "openai",
        "default_model": "gpt-4o-mini",
        "workflow_models": {"rewriting": {"provider": "mock", "model": "mock-deterministic-v1"}},
        "fallback_enabled": True,
        "fallback_provider": "mock",
        "fallback_model": "mock-deterministic-v1",
        "daily_call_limit": 50,
        "monthly_budget_usd": 5,
        "data_residency_ack": True,
    }
    r = client.put(f"{API}/settings", json=payload, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["effective"]["rewriting"]["source"] == "task_override"
    assert body["effective"]["analysis"] == {"provider": "openai", "model": "gpt-4o-mini", "source": "user_default", "usable": True, "problem": None}
    assert body["fallback"]["provider"] == "mock" and body["daily_call_limit"] == 50 and body["monthly_budget_usd"] == 5.0
    assert client.get(f"{API}/status", headers=h).json()["effective"]["provider"] == "openai"
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "ai.settings_updated"))
    assert audit is not None and "default" in audit.meta["changed"]

    # removing the key leaves the choice in place but flags it as unusable
    client.delete(f"{API}/credentials/openai", headers=h)
    body = client.get(f"{API}/settings", headers=h).json()
    assert body["effective"]["analysis"]["usable"] is False and "API key" in body["effective"]["analysis"]["problem"]


def test_users_never_see_each_others_settings_or_keys(client: TestClient, alice: User, bob: User, stub: dict) -> None:
    client.put(f"{API}/credentials/openai", json={"api_key": SECRET}, headers=_auth(alice))
    client.put(f"{API}/settings", json={"default_provider": "openai", "default_model": "gpt-4o-mini", "data_residency_ack": True}, headers=_auth(alice))
    hb = _auth(bob)
    body = client.get(f"{API}/settings", headers=hb).json()
    assert body["default_provider"] is None and body["credentials"] == []
    assert all(p["credential"] is None for p in client.get(f"{API}/providers", headers=hb).json()["providers"])
    assert client.delete(f"{API}/credentials/openai", headers=hb).status_code == 404
    # bob cannot route to openai on alice's key
    assert client.put(f"{API}/settings", json={"default_provider": "openai", "default_model": "gpt-4o-mini", "data_residency_ack": True}, headers=hb).status_code == 422
    _no_secret(*_all_reads(client, hb))


# --------------------------------------------------------------------------- providers / models / usage


def test_provider_catalog_explains_billing_and_privacy(client: TestClient, alice: User, stub: dict) -> None:
    body = client.get(f"{API}/providers", headers=_auth(alice)).json()
    ids = [p["id"] for p in body["providers"]]
    assert ids[:5] == ["ollama", "openai", "gemini", "anthropic", "openai_compatible"]
    assert "billed separately from chat subscriptions" in body["billing_note"]
    gemini = next(p for p in body["providers"] if p["id"] == "gemini")
    assert gemini["hosted"] and gemini["key_url"].startswith("https://") and "resume" in gemini["privacy_note"]
    assert next(p for p in body["providers"] if p["id"] == "mock")["is_server_default"] is True
    assert {w["id"] for w in body["workflows"]} >= {"generation", "analysis", "rewriting", "jd_analysis", "review"}


def test_model_list_merges_live_and_registry(client: TestClient, alice: User, stub: dict) -> None:
    h = _auth(alice)
    # no key yet: registry only, no provider call
    body = client.get(f"{API}/providers/openai/models", headers=h).json()
    assert body["live"] is False and stub["built"] == []
    assert any(m["id"] == "gpt-4o-mini" and m["pricing_known"] for m in body["models"])

    client.put(f"{API}/credentials/openai", json={"api_key": SECRET}, headers=h)
    body = client.get(f"{API}/providers/openai/models?refresh=true", headers=h).json()
    assert body["live"] is True and body["prices_as_of"]
    rows = {m["id"]: m for m in body["models"]}
    assert rows["gpt-4o-mini"]["available"] is True and rows["gpt-4o-mini"]["in_registry"]
    assert rows["gpt-5"]["available"] is False  # in the registry, not offered to this key
    unknown = rows["gpt-9-preview"]
    assert unknown["in_registry"] is False and unknown["pricing_known"] is False and unknown["group"] == "unknown_pricing"
    assert "pricing unknown" in unknown["notes"]

    # live=false reuses the cached live list without a new provider call
    built = len(stub["built"])
    assert client.get(f"{API}/providers/openai/models?live=false", headers=h).json()["live"] is True
    assert len(stub["built"]) == built


def test_test_and_model_endpoints_are_rate_limited(client: TestClient, alice: User, stub: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "AI_TEST_RATE_LIMIT_PER_MINUTE", 2)
    h = _auth(alice)
    codes = [client.post(f"{API}/credentials/mock/test", headers=h).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_usage_endpoint_totals_and_estimates(client: TestClient, db: Session, alice: User, bob: User, stub: dict) -> None:
    for i, (provider, model, cost, status) in enumerate([
        ("openai", "gpt-4o-mini", Decimal("0.0015"), "OK"),
        ("openai", "gpt-4o-mini", Decimal("0.0005"), "OK"),
        ("ollama", "qwen2.5:3b-instruct", Decimal("0"), "FALLBACK"),
        ("openai", "gpt-9-preview", None, "OK"),
        ("openai", "gpt-4o-mini", Decimal("0"), "ERROR"),
    ]):
        db.add(AiUsageEvent(user_id=alice.id, provider=provider, model=model, task="rewrite_bullet", workflow="rewriting",
                            input_tokens=100, output_tokens=50, tokens_estimated=i == 2, estimated_cost_usd=cost,
                            duration_ms=200, status=status, error_code="provider_timeout" if status == "ERROR" else None))
    db.add(AiUsageEvent(user_id=bob.id, provider="openai", model="gpt-4o", task="x", workflow="general", input_tokens=1,
                        output_tokens=1, tokens_estimated=False, estimated_cost_usd=Decimal("9"), duration_ms=1, status="OK"))
    db.commit()
    body = client.get(f"{API}/usage?range=7d", headers=_auth(alice)).json()
    t = body["totals"]
    assert (t["calls"], t["ok"], t["errors"], t["fallbacks"]) == (5, 3, 1, 1)
    assert t["estimated_cost_usd"] == pytest.approx(0.002) and t["cost_unknown_calls"] == 1 and t["tokens_estimated_calls"] == 1
    assert body["estimated"] is True and body["prices_as_of"]["openai"] and "source of truth" in body["note"]
    assert body["by_workflow"][0]["key"] == "rewriting" and body["by_workflow"][0]["label"] == "Bullet rewriting"
    assert len(body["daily"]) == 7 and sum(d["calls"] for d in body["daily"]) == 5
    assert client.get(f"{API}/usage?range=1y", headers=_auth(alice)).status_code == 422


def test_ollama_test_uses_the_local_probe(client: TestClient, alice: User, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.ai.providers import ollama

    def fake_check(base_url: str, model: str, *, client=None):  # noqa: ANN001, ANN202
        return {"base_url": base_url, "model": model, "reachable": True, "model_pulled": True, "version": "0.35.1", "error": None}

    monkeypatch.setattr(ollama, "check_server", fake_check)
    body = client.post(f"{API}/credentials/ollama/test", headers=_auth(alice)).json()
    assert body["ok"] is True and body["model"] == "qwen2.5:3b-instruct" and body["latency_ms"] is not None


def test_endpoints_require_auth(client: TestClient) -> None:
    for method, path in [("get", "/settings"), ("put", "/settings"), ("get", "/providers"), ("get", "/usage"),
                         ("put", "/credentials/openai"), ("post", "/credentials/openai/test")]:
        assert getattr(client, method)(API + path).status_code == 401
