"""Regression tests for the security review (R1).

One test (or small group) per fixed critical/high finding, plus explicit checks for the
safety rails the product deliberately refuses to remove: no Gmail password storage,
read-only Gmail scopes that configuration cannot widen, and no CAPTCHA / OTP / 2FA /
account-registration bypass.

Every test names the finding it guards so a future change that reintroduces the hole
fails here rather than in production.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import DEV_ENCRYPTION_KEY, DEV_SECRET_KEY, Settings, settings
from app.models.application import Application, ApplicationAnswer
from app.models.company import Company
from app.models.email import EmailIntegration
from app.models.enums import (
    AnswerStatus,
    ApplicationStatus,
    ApplicationType,
    AutomationState,
    FieldType,
    JobSourceType,
    PauseReason,
)
from app.models.job import Job
from app.models.user import User

API = "/api/v1"


# --------------------------------------------------------------------------- helpers


def _current_user(client: TestClient, db: Session) -> User:
    me = client.get(f"{API}/auth/me")
    assert me.status_code == 200, me.text
    return db.get(User, uuid.UUID(me.json()["id"]))


def _make_application(db: Session, user: User) -> Application:
    """A minimal QUEUED application with one FILE answer row."""
    company = Company(name="Northwind Labs", normalized_name="northwind labs", domain="northwind.dev")
    db.add(company)
    db.flush()
    now = datetime.now(timezone.utc)
    job = Job(
        company_id=company.id,
        title="Full Stack Engineer",
        normalized_title="full stack engineer",
        description="React and Node.js",
        posted_at=now - timedelta(hours=2),
        canonical_url="https://example.test/job",
        apply_url="https://example.test/apply",
        application_type=ApplicationType.ATS_FORM,
        dedupe_hash=uuid.uuid4().hex,
    )
    db.add(job)
    db.flush()
    application = Application(
        user_id=user.id,
        job_id=job.id,
        status=ApplicationStatus.QUEUED,
        source=JobSourceType.DEMO_ATS,
        automation_state=AutomationState.IDLE,
        form_snapshot={},
        last_update_at=now,
    )
    db.add(application)
    db.flush()
    db.add(
        ApplicationAnswer(
            application_id=application.id,
            order=0,
            question_key="resume_file",
            question_text="Resume/CV",
            field_type=FieldType.FILE,
            required=True,
            answer=str(Path(settings.UPLOAD_DIR) / "resumes" / str(user.id) / "cv.pdf"),
            status=AnswerStatus.ANSWERED,
        )
    )
    db.commit()
    return application


# =========================================================================== H1
# Hardcoded, publicly-known SECRET_KEY / ENCRYPTION_KEY defaults (app/core/config.py).


def test_production_refuses_the_published_development_secret_key() -> None:
    with pytest.raises(Exception) as exc:
        Settings(
            ENV="production",
            SECRET_KEY=DEV_SECRET_KEY,
            ENCRYPTION_KEY="Zm9ya2V5Zm9ya2V5Zm9ya2V5Zm9ya2V5Zm9ya2V5MDA=",
        )
    assert "SECRET_KEY" in str(exc.value)


def test_production_refuses_the_published_development_encryption_key() -> None:
    with pytest.raises(Exception) as exc:
        Settings(ENV="production", SECRET_KEY="x" * 64, ENCRYPTION_KEY=DEV_ENCRYPTION_KEY)
    assert "ENCRYPTION_KEY" in str(exc.value)


def test_production_refuses_a_short_secret_key() -> None:
    with pytest.raises(Exception) as exc:
        Settings(ENV="production", SECRET_KEY="short", ENCRYPTION_KEY="Zm9ya2V5Zm9ya2V5Zm9ya2V5Zm9ya2V5Zm9ya2V5MDA=")
    assert "SECRET_KEY" in str(exc.value)


def test_production_forces_secure_cookies_and_hides_the_docs() -> None:
    production = Settings(
        ENV="production",
        SECRET_KEY="x" * 64,
        ENCRYPTION_KEY="Zm9ya2V5Zm9ya2V5Zm9ya2V5Zm9ya2V5Zm9ya2V5MDA=",
        COOKIE_SECURE=False,
    )
    assert production.COOKIE_SECURE is True, "refresh cookie must never travel over plain HTTP in production"
    assert production.docs_enabled is False


def test_production_refuses_a_wildcard_cors_origin() -> None:
    with pytest.raises(Exception) as exc:
        Settings(
            ENV="production",
            SECRET_KEY="x" * 64,
            ENCRYPTION_KEY="Zm9ya2V5Zm9ya2V5Zm9ya2V5Zm9ya2V5Zm9ya2V5MDA=",
            CORS_ORIGINS=["*"],
        )
    assert "CORS_ORIGINS" in str(exc.value)


def test_development_still_boots_on_the_defaults() -> None:
    dev = Settings(ENV="development", SECRET_KEY=DEV_SECRET_KEY, ENCRYPTION_KEY=DEV_ENCRYPTION_KEY)
    assert dev.SECRET_KEY == DEV_SECRET_KEY and dev.docs_enabled is True


# =========================================================================== H2
# Rate-limit bypass / audit-IP forgery via a client-supplied X-Forwarded-For.


def test_forwarded_for_cannot_pick_a_rate_limit_bucket(client: TestClient) -> None:
    from app.core.config import settings as live

    payload = {"email": "nobody@example.com", "password": "WrongPass123"}
    limit = live.AUTH_RATE_LIMIT_PER_MINUTE
    statuses = [
        client.post(
            f"{API}/auth/login",
            json=payload,
            headers={"X-Forwarded-For": f"10.0.0.{index % 250}"},
        ).status_code
        for index in range(limit + 3)
    ]
    assert 429 in statuses, "a spoofed X-Forwarded-For must not reset the login rate limit"


def test_forwarded_for_is_only_trusted_behind_a_configured_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    from starlette.requests import Request

    from app.core.config import settings as live
    from app.core.rate_limit import client_ip

    scope = {
        "type": "http",
        "headers": [(b"x-forwarded-for", b"203.0.113.7")],
        "client": ("127.0.0.1", 1234),
    }
    request = Request(scope)  # type: ignore[arg-type]

    monkeypatch.setattr(live, "TRUST_PROXY_HEADERS", False)
    assert client_ip(request) == "127.0.0.1"

    monkeypatch.setattr(live, "TRUST_PROXY_HEADERS", True)
    assert client_ip(request) == "203.0.113.7"


def test_a_trusted_proxy_uses_the_peer_not_the_client_supplied_hop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nginx *appends* the peer to X-Forwarded-For, so the left-most hop is attacker input."""
    from starlette.requests import Request

    from app.core.config import settings as live
    from app.core.rate_limit import client_ip

    monkeypatch.setattr(live, "TRUST_PROXY_HEADERS", True)

    spoofed = Request(
        {
            "type": "http",
            "headers": [(b"x-forwarded-for", b"1.2.3.4, 203.0.113.7")],
            "client": ("10.0.0.1", 1234),
        }  # type: ignore[arg-type]
    )
    assert client_ip(spoofed) == "203.0.113.7"

    with_real_ip = Request(
        {
            "type": "http",
            "headers": [(b"x-forwarded-for", b"1.2.3.4"), (b"x-real-ip", b"203.0.113.9")],
            "client": ("10.0.0.1", 1234),
        }  # type: ignore[arg-type]
    )
    assert client_ip(with_real_ip) == "203.0.113.9"


# =========================================================================== H3
# A user-supplied answer for a FILE question became set_input_files(<any path>),
# i.e. arbitrary server-file read with exfiltration to the target site.


def test_file_answers_cannot_be_typed_by_the_user(auth_client: TestClient, db: Session) -> None:
    user = _current_user(auth_client, db)
    application = _make_application(db, user)
    answer_id = str(db.scalars(select(ApplicationAnswer.id)).first())

    response = auth_client.put(
        f"{API}/applications/{application.id}/answers",
        json={"answers": [{"id": answer_id, "answer": "C:/Windows/win.ini"}]},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "file_answer_not_editable"

    db.expire_all()
    stored = db.get(ApplicationAnswer, uuid.UUID(answer_id))
    assert "win.ini" not in (stored.answer or ""), "the attachment path must not be attacker controlled"


def test_autofill_refuses_a_file_outside_the_upload_directory(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.browser.autofill import _resolve_upload_path

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(uploads))

    secret = tmp_path / "dotenv"
    secret.write_text("SECRET_KEY=super-secret", encoding="utf-8")
    path, reason = _resolve_upload_path(str(secret))
    assert path is None and "upload directory" in (reason or "")

    allowed = uploads / "resumes" / "u" / "cv.pdf"
    allowed.parent.mkdir(parents=True)
    allowed.write_bytes(b"%PDF-1.4")
    path, reason = _resolve_upload_path(str(allowed))
    assert path is not None and reason is None


def test_autofill_refuses_traversal_out_of_the_upload_directory(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.browser.autofill import _resolve_upload_path

    uploads = tmp_path / "uploads"
    (uploads / "resumes").mkdir(parents=True)
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(uploads))
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF-1.4")

    path, reason = _resolve_upload_path(str(uploads / "resumes" / ".." / ".." / "outside.pdf"))
    assert path is None and "upload directory" in (reason or "")


# =========================================================================== H4
# /demo-ats/submissions.json leaked every applicant's PII with no authentication.


def test_demo_ats_submissions_do_not_leak_applicant_data(client: TestClient) -> None:
    payload = {
        "first_name": "Aarav",
        "last_name": "Sharma",
        "email": "leak.probe@example.com",
        "phone": "+91 98765 43210",
        "location": "Bangalore",
        "total_experience": "2",
        "react_experience": "2",
        "expected_ctc": "1200000",
        "notice_period": "30 days",
        "work_authorization": "Yes",
        "why_company": "Great product.",
        "start_date": "1 November 2026",
        "consent": "true",
    }
    posted = client.post(
        "/demo-ats/jobs/northwind-labs-full-stack-engineer/apply",
        data=payload,
        files={"resume": ("cv.pdf", b"%PDF-1.4 demo", "application/pdf")},
    )
    assert posted.status_code == 200, posted.text

    body = client.get("/demo-ats/submissions.json")
    assert body.status_code == 200
    raw = body.text
    assert "leak.probe@example.com" not in raw
    assert "98765" not in raw
    assert "1200000" not in raw
    for record in body.json():
        assert "answers" not in record
        assert "resume_path" not in record
        assert "resume_filename" not in record
        assert record["application_id"].startswith("DEMO-")


# =========================================================================== H5
# The demo ATS is the only unauthenticated write on the API: never in production,
# always rate limited, always size capped.


def test_demo_ats_is_not_mounted_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import create_app
    from app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "ENV", "production")
    paths = {route.path for route in create_app().routes}
    assert not any(path.startswith("/demo-ats") for path in paths)
    assert "/docs" not in paths and "/openapi.json" not in paths
    assert f"{API}/auth/login" in paths, "the real API must still be mounted"


def test_demo_ats_apply_is_rate_limited(client: TestClient) -> None:
    from app.demo_ats.router import DEMO_SUBMIT_LIMIT_PER_MINUTE

    data = {"email": "flood@example.com", "consent": ""}
    statuses = [
        client.post("/demo-ats/jobs/northwind-labs-full-stack-engineer/apply", data=data).status_code
        for _ in range(DEMO_SUBMIT_LIMIT_PER_MINUTE + 2)
    ]
    assert 429 in statuses, "anonymous demo submissions must not be unlimited"


def test_demo_ats_rejects_an_oversized_resume(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    oversized = b"%PDF-1.4" + b"0" * (1024 * 1024 + 4096)
    response = client.post(
        "/demo-ats/jobs/northwind-labs-full-stack-engineer/apply",
        data={"email": "big@example.com", "consent": "true"},
        files={"resume": ("big.pdf", oversized, "application/pdf")},
    )
    assert response.status_code == 422
    assert "too large" in response.text


# =========================================================================== H6
# Resume upload buffered the whole body before checking the size limit.


def test_resume_upload_stops_reading_past_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from app.core.exceptions import ValidationFailed
    from app.modules.resumes import storage

    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)

    class CountingStream(io.RawIOBase):
        """A stream that would hand over far more than the limit if asked."""

        def __init__(self) -> None:
            self.served = 0

        def read(self, size: int = -1) -> bytes:  # noqa: D401
            chunk = b"x" * (size if size and size > 0 else 4096)
            self.served += len(chunk)
            return chunk

    stream = CountingStream()
    with pytest.raises(ValidationFailed) as exc:
        storage.read_within_limit(stream)
    assert exc.value.code == "file_too_large"
    # never buffers meaningfully more than the limit itself
    assert stream.served <= storage.max_upload_bytes() + storage.READ_CHUNK_BYTES


def test_oversized_resume_upload_is_rejected_over_http(auth_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    response = auth_client.post(
        f"{API}/resumes",
        files={"file": ("big.pdf", b"%PDF-1.4" + b"0" * (1024 * 1024 + 4096), "application/pdf")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "file_too_large"


# =========================================================================== H7
# Gmail OAuth account-linking CSRF: the state was not bound to the browser that
# started the flow, so a victim's mailbox could be attached to an attacker's account.


@pytest.fixture
def google_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "client-secret")
    yield


def test_gmail_callback_without_the_state_cookie_is_rejected(
    client: TestClient, auth_client: TestClient, db: Session, google_configured, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.integrations import gmail_oauth

    user = _current_user(auth_client, db)
    integration = gmail_oauth.get_or_create_integration(db, user.id)
    state = gmail_oauth.new_state()
    integration.oauth_state = state
    db.commit()

    def _boom(code, state=None):  # pragma: no cover - must never run
        raise AssertionError("the code must not be exchanged without a matching cookie")

    monkeypatch.setattr(gmail_oauth, "exchange_code", _boom)

    # the attacker replays their own state from a browser that never started the flow
    client.cookies.clear()
    response = client.get(
        f"{API}/integrations/gmail/callback",
        params={"code": "victim-auth-code", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "error=state_mismatch" in response.headers["location"]

    db.expire_all()
    stored = db.scalars(select(EmailIntegration).where(EmailIntegration.user_id == user.id)).first()
    assert stored.encrypted_credentials is None
    assert stored.oauth_state is None, "the state must be burnt so the link cannot be retried"


def test_gmail_callback_rejects_a_stale_state(
    client: TestClient, auth_client: TestClient, db: Session, google_configured, monkeypatch: pytest.MonkeyPatch
) -> None:
    import time

    from app.modules.integrations import gmail_oauth

    user = _current_user(auth_client, db)
    integration = gmail_oauth.get_or_create_integration(db, user.id)
    issued = int(time.time()) - gmail_oauth.STATE_TTL_SECONDS - 60
    state = f"{issued}.expired-nonce"
    integration.oauth_state = state
    db.commit()

    monkeypatch.setattr(gmail_oauth, "exchange_code", lambda code, state=None: {})
    client.cookies.set(gmail_oauth.STATE_COOKIE_NAME, state)
    response = client.get(
        f"{API}/integrations/gmail/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "error=invalid_state" in response.headers["location"]


def test_the_oauth_error_is_not_reflected_verbatim(client: TestClient) -> None:
    """Whatever Google (or an attacker) puts in ``error`` must not reach the redirect raw."""
    for probe in ("x\r\nSet-Cookie: a=b", "//evil.com", "x#@evil.com", "<script>alert(1)</script>"):
        response = client.get(
            f"{API}/integrations/gmail/callback", params={"error": probe}, follow_redirects=False
        )
        location = response.headers["location"]
        prefix = f"{settings.FRONTEND_URL}/emails?error="
        assert location.startswith(prefix)
        reflected = location[len(prefix) :]
        # an opaque code: nothing that can change the target, add a header or carry markup
        assert all(ch.isalnum() or ch in "_-." for ch in reflected), reflected


def test_gmail_connect_sets_the_httponly_state_cookie(auth_client: TestClient, google_configured) -> None:
    from app.modules.integrations import gmail_oauth

    response = auth_client.post(f"{API}/integrations/gmail/connect")
    assert response.status_code == 200, response.text
    raw = response.headers.get("set-cookie", "")
    assert gmail_oauth.STATE_COOKIE_NAME in raw
    assert "HttpOnly" in raw
    assert auth_client.cookies.get(gmail_oauth.STATE_COOKIE_NAME) in response.json()["authorization_url"]


# =========================================================================== deliberate refusals
# The product promises these are impossible; verify they are impossible in code.


def test_no_gmail_password_is_ever_requested_or_stored(db: Session) -> None:
    from app.modules.integrations.schemas import ConnectedAccountCreate, GmailStatus

    # the Gmail integration row has no password/credential column beyond the encrypted
    # OAuth bundle, and the API view exposes neither
    columns = set(EmailIntegration.__table__.columns.keys())
    assert not {"password", "app_password", "hashed_password"} & columns
    assert "encrypted_credentials" in columns
    assert "token" not in set(GmailStatus.model_fields)
    assert "credentials" not in set(GmailStatus.model_fields)

    # platform credentials exist, but Gmail is not a job source, so they can never be
    # a mailbox password
    assert not hasattr(JobSourceType, "GMAIL")
    assert set(ConnectedAccountCreate.model_fields) == {"source", "account_identifier", "credentials"}


def test_gmail_scopes_are_read_only_and_cannot_be_widened_by_configuration() -> None:
    assert settings.GMAIL_SCOPES == [
        "https://www.googleapis.com/auth/gmail.readonly",
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
    ]
    for forbidden in (
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.compose",
        "https://mail.google.com/",
    ):
        with pytest.raises(Exception):
            Settings(GMAIL_SCOPES=[forbidden])


def test_a_write_capable_scope_returned_by_google_is_refused() -> None:
    from app.core.exceptions import ValidationFailed
    from app.modules.integrations.gmail_oauth import _assert_scopes_are_read_only

    with pytest.raises(ValidationFailed):
        _assert_scopes_are_read_only(["https://www.googleapis.com/auth/gmail.modify"])
    _assert_scopes_are_read_only(["https://www.googleapis.com/auth/gmail.readonly", "openid"])


def test_the_gmail_client_never_calls_a_write_endpoint() -> None:
    source = Path("app/modules/emails/gmail_client.py").read_text(encoding="utf-8")
    for forbidden in (".send(", ".trash(", ".modify(", ".delete(", ".batchModify(", ".insert("):
        assert forbidden not in source, f"gmail_client must stay read-only ({forbidden})"


def test_captcha_is_detected_and_never_solved() -> None:
    from app.modules.browser.detector import detect_form_from_html

    html = """
    <html><body><form>
      <label for="e">Email</label><input id="e" name="email">
      <div class="g-recaptcha" data-sitekey="abc"></div>
      <button type="submit">Submit Application</button>
    </form></body></html>
    """
    blockers = detect_form_from_html(html).blockers
    assert [b.kind for b in blockers] == [PauseReason.CAPTCHA]
    assert "never solves" in blockers[0].message


def test_otp_and_two_factor_prompts_pause_instead_of_being_answered() -> None:
    from app.modules.browser.detector import detect_form_from_html

    html = """
    <html><body><form>
      <label for="c">Enter the one-time code we sent you</label>
      <input id="c" name="otp" autocomplete="one-time-code">
      <button type="submit">Verify</button>
    </form></body></html>
    """
    kinds = [b.kind for b in detect_form_from_html(html).blockers]
    assert PauseReason.OTP in kinds


def test_account_registration_prompt_pauses_for_the_user() -> None:
    from app.modules.browser.detector import detect_form_from_html

    html = """
    <html><body><h2>Create an account to apply</h2><form>
      <label for="e">Email</label><input id="e" name="email" type="email">
      <label for="p1">Password</label><input id="p1" name="password" type="password">
      <label for="p2">Confirm Password</label><input id="p2" name="confirm_password" type="password">
      <button type="submit">Register</button>
    </form></body></html>
    """
    blockers = detect_form_from_html(html).blockers
    assert [b.kind for b in blockers] == [PauseReason.ACCOUNT_REGISTRATION_REQUIRED]
    assert "register yourself" in blockers[0].message


def test_an_ats_adapter_pauses_with_requires_user_on_any_blocker() -> None:
    """The adapter must hand control back, never work around the blocker."""
    from app.modules.adapters.base import ApplyContext
    from app.modules.adapters.demo_ats import DemoAtsAdapter
    from app.modules.browser.schemas import Blocker, DetectedForm

    blocked = DetectedForm(
        url="https://example.test/apply",
        blockers=[Blocker(kind=PauseReason.ACCOUNT_REGISTRATION_REQUIRED, selector="#p", message="register first")],
    )

    class _Page:
        pass

    adapter = DemoAtsAdapter()
    ctx = ApplyContext(application=None, job=None, candidate=None, answers=[], page=_Page())
    import app.modules.browser.detector as detector

    original = detector.detect_form
    detector.detect_form = lambda page: blocked  # type: ignore[assignment]
    try:
        result = adapter.fill_application(ctx)
    finally:
        detector.detect_form = original  # type: ignore[assignment]

    assert result.state == AutomationState.REQUIRES_USER
    assert result.pause_reason == PauseReason.ACCOUNT_REGISTRATION_REQUIRED


def test_the_browser_only_navigates_to_http_urls() -> None:
    """A bad listing must not be able to point the automation at file:// or javascript:."""
    from app.modules.adapters.base import ApplyContext
    from app.modules.adapters.demo_ats import DemoAtsAdapter

    class _Job:
        canonical_url = None

        def __init__(self, url: str) -> None:
            self.apply_url = url

    class _Page:
        def __init__(self) -> None:
            self.visited: list[str] = []

        def goto(self, url: str, **_: object) -> None:  # pragma: no cover - must not run
            self.visited.append(url)

        def wait_for_selector(self, *_: object, **__: object) -> None:  # pragma: no cover
            pass

    adapter = DemoAtsAdapter()
    for hostile in ("file:///etc/passwd", "javascript:alert(1)", "data:text/html,<form></form>"):
        page = _Page()
        result = adapter.start_application(ApplyContext(job=_Job(hostile), page=page))
        assert result.state == AutomationState.FAILED
        assert page.visited == [], f"must never navigate to {hostile}"

    page = _Page()
    assert adapter.start_application(ApplyContext(job=_Job("http://localhost:8000/demo-ats/x/apply"), page=page))
    assert page.visited == ["http://localhost:8000/demo-ats/x/apply"]


def test_no_captcha_solving_dependency_or_stealth_plugin_is_present() -> None:
    requirements = Path("requirements.txt").read_text(encoding="utf-8").lower()
    for forbidden in ("2captcha", "anticaptcha", "anti-captcha", "capmonster", "playwright-stealth", "undetected"):
        assert forbidden not in requirements, f"{forbidden} must never be a dependency"


def test_encrypted_columns_are_never_returned_by_the_api(auth_client: TestClient, db: Session) -> None:
    """Connected-account credentials are exposed only as a boolean."""
    response = auth_client.post(
        f"{API}/integrations/accounts",
        json={
            "source": JobSourceType.LINKEDIN.value,
            "account_identifier": "aarav@example.com",
            "credentials": {"username": "aarav@example.com", "password": "PlatformPass123!"},
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["has_credentials"] is True
    assert "PlatformPass123!" not in json.dumps(body)
    assert "encrypted_credentials" not in body

    listed = auth_client.get(f"{API}/integrations/accounts")
    assert "PlatformPass123!" not in listed.text
    assert "encrypted_credentials" not in listed.text


# ------------------------------------------------- the quick start must still start

PLACEHOLDER_ENCRYPTION_KEY = "generate-your-own-fernet-key-see-command-above"


def test_development_boots_on_the_env_example_placeholder_key() -> None:
    """``cp .env.example .env && docker compose up`` has to work.

    The example file ships a placeholder instead of a working Fernet key so nobody
    deploys with a secret published in this repository. Outside production that
    placeholder falls back to the development key rather than failing at import with
    an error that never mentions which setting is wrong.
    """
    development = Settings(ENV="development", ENCRYPTION_KEY=PLACEHOLDER_ENCRYPTION_KEY)

    assert development.ENCRYPTION_KEY == DEV_ENCRYPTION_KEY

    from app.core.security import SecretBox

    box = SecretBox(development.ENCRYPTION_KEY)
    assert box.decrypt(box.encrypt("token")) == "token"


def test_production_refuses_the_placeholder_encryption_key() -> None:
    """The same placeholder must stop a production boot, not fail at first encryption."""
    with pytest.raises(ValueError, match="valid Fernet key"):
        Settings(ENV="production", SECRET_KEY="x" * 64, ENCRYPTION_KEY=PLACEHOLDER_ENCRYPTION_KEY)


def test_production_accepts_a_freshly_generated_key() -> None:
    from cryptography.fernet import Fernet

    production = Settings(ENV="production", SECRET_KEY="x" * 64, ENCRYPTION_KEY=Fernet.generate_key().decode())

    assert production.COOKIE_SECURE is True
    assert production.docs_enabled is False


# --------------------------------------------- configuration actually reaches the app

def test_comma_separated_list_settings_parse_from_the_environment() -> None:
    """``CORS_ORIGINS=a,b`` is the form every .env and docker compose env var uses.

    pydantic-settings runs ``json.loads`` on a list field before any validator sees it,
    so without ``NoDecode`` the plain comma-separated form raised SettingsError at
    startup — which would have taken down ``docker compose up`` as well as a local run.
    """
    plain = Settings(_env_file=None, CORS_ORIGINS="http://a.test,http://b.test")
    assert plain.CORS_ORIGINS == ["http://a.test", "http://b.test"]

    # The JSON-array form has to keep working for anyone already using it.
    as_json = Settings(_env_file=None, CORS_ORIGINS='["http://c.test"]')
    assert as_json.CORS_ORIGINS == ["http://c.test"]


def test_settings_read_the_repo_root_env_file_from_any_working_directory() -> None:
    """The backend must find the same ``.env`` Compose uses, wherever it is launched from.

    ``env_file=".env"`` resolves against the *current* directory, so running from
    ``backend/`` silently fell back to the built-in defaults — including the development
    secrets published in this repository — with nothing to warn the operator.
    """
    from app.core.config import ENV_FILES, REPO_ROOT

    assert ENV_FILES[0] == REPO_ROOT / ".env"
    assert (REPO_ROOT / "docker-compose.yml").exists(), "REPO_ROOT should be the directory holding docker-compose.yml"
