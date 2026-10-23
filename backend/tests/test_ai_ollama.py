"""Tests for the local Ollama provider (``LLM_PROVIDER=ollama``).

Everything except the last test runs against ``httpx.MockTransport``: no Ollama server
and no network are needed. The live test is opt-in (``JOBPILOT_LIVE_OLLAMA=1``) and only
ever talks to the local server.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ExternalServiceError
from app.core.security import create_access_token, hash_password
from app.models.user import User
from app.modules.ai import factory
from app.modules.ai.factory import get_llm_provider, provider_status, reset_llm_provider
from app.modules.ai.providers import ollama
from app.modules.ai.providers.ollama import OllamaProvider
from app.modules.ai.schemas import EmailClassificationResult

BASE_URL = "http://ollama.test:11434"
MODEL = "qwen2.5:3b-instruct"

Handler = Callable[[httpx.Request], httpx.Response]


class Recorder:
    """A MockTransport handler that records every request and answers from a script."""

    def __init__(self, *chat_replies: Any, tags: list[str] | None = None, version: str = "0.35.1") -> None:
        self.chat_replies = list(chat_replies)
        self.tags = [MODEL] if tags is None else tags
        self.version = version
        self.requests: list[httpx.Request] = []

    @property
    def chat_bodies(self) -> list[dict[str, Any]]:
        return [json.loads(r.content) for r in self.requests if r.url.path == "/api/chat"]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": n, "model": n} for n in self.tags]})
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": self.version})
        if request.url.path == "/api/chat":
            reply = self.chat_replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            if isinstance(reply, httpx.Response):
                return reply
            return httpx.Response(200, json={"model": MODEL, "message": {"role": "assistant", "content": reply}, "done": True})
        return httpx.Response(404, json={"error": "not found"})


def make_provider(handler: Handler, **kwargs: Any) -> OllamaProvider:
    return OllamaProvider(base_url=BASE_URL, model=MODEL, transport=httpx.MockTransport(handler), **kwargs)


def refuse(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("[WinError 10061] connection refused", request=request)


class Tiny(BaseModel):
    city: str
    count: int


# --------------------------------------------------------------------------- complete


def test_complete_posts_a_non_streaming_chat_request() -> None:
    rec = Recorder("Hello there.")
    provider = make_provider(rec, keep_alive="10m", num_ctx=4096)

    text = provider.complete("Say hello", system="Be brief.", max_tokens=50, temperature=0.7)

    assert text == "Hello there."
    (body,) = rec.chat_bodies
    assert body["model"] == MODEL
    assert body["stream"] is False
    assert body["keep_alive"] == "10m"
    assert body["messages"] == [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Say hello"}]
    assert body["options"] == {"temperature": 0.7, "num_predict": 50, "num_ctx": 4096}
    assert "format" not in body


def test_complete_rejects_an_empty_reply() -> None:
    provider = make_provider(Recorder("   "))
    with pytest.raises(ExternalServiceError) as err:
        provider.complete("Say hello")
    assert err.value.code == "llm_empty_response"


# --------------------------------------------------------------------------- complete_json


def test_complete_json_constrains_output_with_the_schema() -> None:
    rec = Recorder('{"classification": "OFFER", "confidence": 0.9, "reason": "Offer letter attached."}')
    provider = make_provider(rec)

    data = provider.complete_json("Classify this email", schema=EmailClassificationResult, system="You classify email.")

    assert data["classification"] == "OFFER"
    (body,) = rec.chat_bodies
    expected = EmailClassificationResult.model_json_schema()
    assert body["format"]["properties"] == expected["properties"]
    # Non-nullable keys are required in the grammar, so a small model cannot skip "reason";
    # the nullable hints stay optional.
    assert body["format"]["required"] == ["classification", "confidence", "reason"]
    assert body["options"]["temperature"] == 0.1
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][0]["content"].startswith("You classify email.")
    assert "JSON object" in body["messages"][0]["content"]


def test_strict_schema_requires_non_nullable_keys_without_touching_the_original() -> None:
    from app.modules.ai.schemas import GeneratedAnswer, ParsedResume

    original = ParsedResume.model_json_schema()
    strict = ollama.strict_schema(original)
    assert "required" not in original  # pydantic marks defaulted fields optional
    assert strict["required"] == [
        "skills", "experience", "education", "projects", "certifications", "links",
        "achievements", "languages", "section_order",
    ]
    assert strict["$defs"]["ExperienceEntry"]["required"] == ["technologies"]
    assert strict["properties"] == original["properties"]  # only "required" changes

    # A nullable key the model may have nothing for stays optional (forcing it caused
    # runaway strings in the prompt-fit check).
    answer = ollama.strict_schema(GeneratedAnswer.model_json_schema())
    assert "question_key" not in answer["required"] and "answer" not in answer["required"]
    assert {"source", "confidence", "rationale", "needs_user_input"} <= set(answer["required"])


def test_strict_schema_keeps_fields_that_were_already_required() -> None:
    strict = ollama.strict_schema(Tiny.model_json_schema())
    assert strict["required"] == ["city", "count"]


def test_complete_json_without_a_schema_uses_json_mode() -> None:
    rec = Recorder('```json\n{"ok": true}\n```')  # fences are still stripped
    provider = make_provider(rec)

    assert provider.complete_json("Return ok", schema=None) == {"ok": True}
    assert rec.chat_bodies[0]["format"] == "json"


def test_complete_json_honours_a_task_temperature() -> None:
    rec = Recorder('{"city": "Pune", "count": 2}')
    make_provider(rec).complete_json("x", schema=Tiny, temperature=0.4)
    assert rec.chat_bodies[0]["options"]["temperature"] == 0.4


def test_complete_json_retries_once_with_a_json_nudge() -> None:
    rec = Recorder("Sure! The city is Pune.", '{"city": "Pune", "count": 2}')
    provider = make_provider(rec)

    assert provider.complete_json("Where?", schema=Tiny) == {"city": "Pune", "count": 2}

    first, second = rec.chat_bodies
    assert len(second["messages"]) == len(first["messages"]) + 2
    assert second["messages"][-2] == {"role": "assistant", "content": "Sure! The city is Pune."}
    nudge = second["messages"][-1]
    assert nudge["role"] == "user" and "Return only the JSON object" in nudge["content"]


def test_complete_json_retries_when_the_json_misses_the_schema() -> None:
    rec = Recorder('{"city": "Pune"}', '{"city": "Pune", "count": 3}')
    assert make_provider(rec).complete_json("Where?", schema=Tiny) == {"city": "Pune", "count": 3}
    assert "did not match the schema" in rec.chat_bodies[1]["messages"][-1]["content"]


def test_complete_json_returns_parseable_json_after_the_retry_even_if_off_schema() -> None:
    """The task layer validates and falls back; the provider only guarantees JSON."""
    rec = Recorder('{"city": "Pune"}', '{"city": "Pune", "count": "many"}')
    assert make_provider(rec).complete_json("Where?", schema=Tiny) == {"city": "Pune", "count": "many"}


def test_a_truncated_reply_is_retried_with_a_shorter_nudge() -> None:
    cut_off = httpx.Response(
        200, json={"message": {"role": "assistant", "content": '{"city": "Pu'}, "done": True, "done_reason": "length"}
    )
    rec = Recorder(cut_off, '{"city": "Pune", "count": 1}')
    assert make_provider(rec).complete_json("Where?", schema=Tiny, max_tokens=5) == {"city": "Pune", "count": 1}
    nudge = rec.chat_bodies[1]["messages"][-1]["content"]
    assert "cut off at the 5-token limit" in nudge


def test_complete_json_gives_up_after_one_retry() -> None:
    rec = Recorder("not json", "still not json")
    with pytest.raises(ExternalServiceError) as err:
        make_provider(rec).complete_json("Where?", schema=Tiny)
    assert err.value.code == "llm_bad_json"
    assert "after a retry" in err.value.message
    assert len(rec.chat_bodies) == 2


# --------------------------------------------------------------------------- failure modes


def test_server_down_is_reported_clearly() -> None:
    provider = make_provider(refuse)
    with pytest.raises(ExternalServiceError) as err:
        provider.complete("hi")
    assert err.value.code == "llm_unavailable"
    assert "ollama serve" in err.value.message
    assert BASE_URL in err.value.message


def test_model_not_pulled_is_reported_clearly() -> None:
    missing = httpx.Response(404, json={"error": f"model '{MODEL}' not found"})
    with pytest.raises(ExternalServiceError) as err:
        make_provider(Recorder(missing)).complete_json("x", schema=Tiny)
    assert err.value.code == "llm_model_missing"
    assert f"ollama pull {MODEL}" in err.value.message
    assert err.value.details == {"ollama_error": f"model '{MODEL}' not found"}


def test_timeout_is_reported_clearly() -> None:
    rec = Recorder(httpx.ReadTimeout("timed out"))
    with pytest.raises(ExternalServiceError) as err:
        make_provider(rec, timeout=5).complete("hi")
    assert err.value.code == "llm_timeout"
    assert "5s" in err.value.message and "LLM_TIMEOUT_SECONDS" in err.value.message


def test_other_http_errors_carry_the_ollama_message() -> None:
    rec = Recorder(httpx.Response(500, json={"error": "out of memory"}))
    with pytest.raises(ExternalServiceError) as err:
        make_provider(rec).complete("hi")
    assert err.value.code == "llm_request_failed"
    assert "out of memory" in err.value.message


# --------------------------------------------------------------------------- introspection


def test_is_configured_when_the_server_answers_and_the_model_is_pulled() -> None:
    assert make_provider(Recorder(tags=["llama3:latest", MODEL])).is_configured is True


def test_is_configured_matches_an_implicit_latest_tag() -> None:
    provider = OllamaProvider(
        base_url=BASE_URL, model="qwen2.5", transport=httpx.MockTransport(Recorder(tags=["qwen2.5:latest"]))
    )
    assert provider.is_configured is True


def test_not_configured_when_the_model_is_missing() -> None:
    assert make_provider(Recorder(tags=["qwen2.5:7b-instruct"])).is_configured is False


def test_not_configured_when_the_server_is_down() -> None:
    assert make_provider(refuse).is_configured is False


def test_describe_reports_server_model_and_version() -> None:
    info = make_provider(Recorder(version="0.35.1")).describe()
    assert info == {
        "provider": "ollama",
        "model": MODEL,
        "configured": True,
        "base_url": BASE_URL,
        "reachable": True,
        "model_pulled": True,
        "version": "0.35.1",
        "error": None,
    }


def test_describe_explains_a_missing_model() -> None:
    info = make_provider(Recorder(tags=[])).describe()
    assert info["configured"] is False and info["reachable"] is True and info["model_pulled"] is False
    assert f"ollama pull {MODEL}" in info["error"]


def test_describe_when_the_server_is_down() -> None:
    info = make_provider(refuse).describe()
    assert info["configured"] is False and info["reachable"] is False and info["version"] is None
    assert "ollama serve" in info["error"]


# --------------------------------------------------------------------------- settings


def test_defaults_come_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_MODEL", None)
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434/")
    monkeypatch.setattr(settings, "OLLAMA_KEEP_ALIVE", "0")
    monkeypatch.setattr(settings, "OLLAMA_NUM_CTX", 2048)
    rec = Recorder("ok")
    provider = OllamaProvider(transport=httpx.MockTransport(rec))
    provider.complete("hi")

    assert provider.model == ollama.DEFAULT_MODEL == "qwen2.5:3b-instruct"
    assert provider.base_url == "http://localhost:11434"
    body = rec.chat_bodies[0]
    assert body["keep_alive"] == 0  # a bare number is sent as seconds, "0" unloads at once
    assert body["options"]["num_ctx"] == 2048


def test_timeout_defaults_to_at_least_120_seconds() -> None:
    assert ollama.timeout_for(60, explicit=False) == 120.0  # the global default is too short
    assert ollama.timeout_for(300, explicit=False) == 300.0
    # An explicit LLM_TIMEOUT_SECONDS is respected, even when it is lower.
    assert ollama.timeout_for(30, explicit=True) == 30.0


# --------------------------------------------------------------------------- factory / status


@pytest.fixture
def api(client: TestClient, db: Session) -> TestClient:
    """Authenticated client with a token minted directly (keeps this file independent
    of the auth module's register flow)."""
    user = User(email="ollama-tester@example.com", hashed_password=hash_password("StrongPass123!"), full_name="Ollama Tester", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    client.headers.update({"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"})
    return client


@pytest.fixture
def ollama_selected(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """Select the ollama provider and route its health probe to a mock server."""
    rec = Recorder(tags=[MODEL])
    real_check = ollama.check_server

    def fake_check(base_url: str, model: str, *, client: httpx.Client | None = None) -> dict[str, Any]:
        mock_client = httpx.Client(base_url=base_url, transport=httpx.MockTransport(rec))
        try:
            return real_check(base_url, model, client=mock_client)
        finally:
            mock_client.close()

    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "LLM_MODEL", None)
    monkeypatch.setattr(ollama, "check_server", fake_check)
    reset_llm_provider()
    yield rec
    reset_llm_provider()


def test_factory_builds_the_ollama_provider(ollama_selected: Recorder) -> None:
    provider = get_llm_provider()
    assert isinstance(provider, OllamaProvider)
    assert provider.model == "qwen2.5:3b-instruct"
    assert provider.supports_task("parse_resume") is False  # real model, no rule shortcut
    assert factory.DEFAULT_MODELS["ollama"] == "qwen2.5:3b-instruct"


def test_provider_status_reports_ollama(ollama_selected: Recorder) -> None:
    status = provider_status()
    assert status["provider"] == "ollama"
    assert status["model"] == "qwen2.5:3b-instruct"
    assert status["configured"] is True
    assert status["model_pulled"] is True
    assert status["version"] == "0.35.1"


def test_provider_status_is_not_configured_without_the_model(ollama_selected: Recorder) -> None:
    ollama_selected.tags = []
    status = provider_status()
    assert status["configured"] is False
    assert "ollama pull" in status["error"]


def test_status_endpoint_shows_ollama(ollama_selected: Recorder, api: TestClient) -> None:
    response = api.get("/api/v1/ai/status")
    assert response.status_code == 200, response.text
    body = response.json()
    body.pop("effective", None)  # the signed-in user's setup (AI Model Settings)
    assert body == {"provider": "ollama", "model": "qwen2.5:3b-instruct", "configured": True}


def test_mock_status_ignores_llm_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """A .env that names an ollama model must not relabel the mock."""
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    monkeypatch.setattr(settings, "LLM_MODEL", "qwen2.5:3b-instruct")
    assert provider_status() == {"provider": "mock", "model": "mock-deterministic-v1", "configured": True}


# --------------------------------------------------------------------------- live (opt-in)


@pytest.mark.skipif(os.getenv("JOBPILOT_LIVE_OLLAMA") != "1", reason="set JOBPILOT_LIVE_OLLAMA=1 to call the local Ollama server")
def test_live_complete_json_against_the_local_server() -> None:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("JOBPILOT_LIVE_OLLAMA_MODEL", ollama.DEFAULT_MODEL)
    provider = OllamaProvider(base_url=base_url, model=model, timeout=180, keep_alive=0)
    if not provider.is_configured:
        pytest.skip(provider.describe()["error"])
    try:
        data = provider.complete_json(
            "Pune is a city in India. It has 3 well-known IT parks. Report the city and the number of IT parks.",
            schema=Tiny,
            max_tokens=100,
        )
    finally:
        provider.close()
    parsed = Tiny.model_validate(data)
    assert parsed.city.lower() == "pune"
    assert parsed.count == 3
