"""Tests for the integrations module: Gmail OAuth, sync and platform accounts (§13)."""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token, decrypt_str, encrypt_str, hash_password
from app.models.audit import AuditLog
from app.models.automation import ConnectedAccount
from app.models.base import utcnow
from app.models.company import Company
from app.models.email import EmailIntegration, EmailMessage
from app.models.enums import ApplicationStatus, ApplicationType, IntegrationStatus, JobSourceType
from app.models.job import Job
from app.models.application import Application
from app.models.user import User
from app.modules.companies.service import normalize_company_name
from app.modules.emails import service as emails_service
from app.modules.emails.schemas import IncomingEmail
from app.modules.integrations import gmail_oauth, service
from app.modules.integrations.schemas import ConnectedAccountCreate

API = "/api/v1/integrations"


# --------------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _local_status_updates(monkeypatch):
    """The applications module is written in parallel; keep status changes local."""
    monkeypatch.setattr(emails_service, "_applications_service", lambda: None)


@pytest.fixture
def user(db) -> User:
    row = User(
        email="integrations-tester@example.com",
        hashed_password=hash_password("StrongPass123!"),
        full_name="Integrations Tester",
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def api(client, user):
    token = create_access_token(user.id, user.role.value)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.fixture
def google_configured(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret")
    return settings


@pytest.fixture
def connected_integration(db, user) -> EmailIntegration:
    integration = EmailIntegration(
        user_id=user.id,
        email_address="candidate@gmail.com",
        encrypted_credentials=encrypt_str(json.dumps({"token": "access-1", "refresh_token": "refresh-1", "scopes": list(settings.GMAIL_SCOPES)})),
        scopes=list(settings.GMAIL_SCOPES),
        status=IntegrationStatus.CONNECTED,
        connected_at=utcnow(),
    )
    db.add(integration)
    db.commit()
    return integration


def make_application(db, user: User, *, company_name: str = "Acme Cloud", domain: str = "acmecloud.com") -> Application:
    company = Company(name=company_name, normalized_name=normalize_company_name(company_name), domain=domain)
    db.add(company)
    db.flush()
    job = Job(
        company_id=company.id,
        title="Senior Backend Engineer",
        normalized_title="senior backend engineer",
        description="Build APIs.",
        dedupe_hash=uuid.uuid4().hex,
        application_type=ApplicationType.ATS_FORM,
    )
    db.add(job)
    db.flush()
    application = Application(
        user_id=user.id,
        job_id=job.id,
        status=ApplicationStatus.APPLIED,
        source=JobSourceType.DEMO_ATS,
        applied_at=utcnow(),
    )
    db.add(application)
    db.commit()
    return application


class FakeGmail:
    """Stand-in for :class:`GmailClient` (no network, no google libraries)."""

    def __init__(self, messages: list[IncomingEmail], *, refreshed: bool = False, credentials: dict | None = None) -> None:
        self._messages = {msg.provider_message_id: msg for msg in messages}
        self.refreshed = refreshed
        self._credentials = credentials or {}
        self.listed_with: dict | None = None

    def list_job_related_messages(self, max_results: int = 50, newer_than_days: int = 30) -> list[str]:
        self.listed_with = {"max_results": max_results, "newer_than_days": newer_than_days}
        return list(self._messages)

    def get_message(self, message_id: str) -> IncomingEmail:
        return self._messages[message_id]

    def credentials_json_dict(self) -> dict:
        return dict(self._credentials)


def _incoming(subject: str, sender: str, body: str, message_id: str) -> IncomingEmail:
    return IncomingEmail(
        provider_message_id=message_id,
        sender=sender,
        recipient="candidate@gmail.com",
        subject=subject,
        body_text=body,
        received_at=utcnow(),
    )


# --------------------------------------------------------------------------- overview


def test_overview_without_google_configured(api, db, user):
    response = api.get(API)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["gmail"]["configured"] is False
    assert body["gmail"]["status"] == IntegrationStatus.DISCONNECTED.value
    assert body["gmail"]["email_address"] is None
    assert body["accounts"] == []
    assert len(body["adapters"]) >= 10
    sources = {adapter["source"] for adapter in body["adapters"]}
    assert {"LINKEDIN", "NAUKRI", "DEMO_ATS"} <= sources
    assert all("terms_note" in adapter for adapter in body["adapters"])


def test_overview_reports_configuration(api, google_configured):
    assert api.get(API).json()["gmail"]["configured"] is True


def test_integrations_require_authentication(client):
    assert client.get(API).status_code == 401
    assert client.post(f"{API}/gmail/connect").status_code == 401


# --------------------------------------------------------------------------- gmail oauth


def test_connect_without_configuration_is_422(api):
    response = api.post(f"{API}/gmail/connect")
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "not_configured"


def test_connect_returns_a_read_only_authorization_url(api, db, user, google_configured):
    response = api.post(f"{API}/gmail/connect")
    assert response.status_code == 200, response.text
    url = response.json()["authorization_url"]
    assert url.startswith("https://accounts.google.com/o/oauth2/auth")
    assert "gmail.readonly" in url
    assert "gmail.send" not in url and "gmail.modify" not in url
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "include_granted_scopes=false" in url

    db.expire_all()
    integration = db.scalars(select(EmailIntegration).where(EmailIntegration.user_id == user.id)).first()
    assert integration is not None
    assert integration.oauth_state and integration.oauth_state in url
    assert integration.status is IntegrationStatus.DISCONNECTED


def test_callback_rejects_an_unknown_state(client, db, google_configured):
    response = client.get(f"{API}/gmail/callback", params={"code": "abc", "state": "nope"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == f"{settings.FRONTEND_URL}/emails?error=invalid_state"


def test_callback_forwards_a_google_error(client):
    response = client.get(f"{API}/gmail/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].endswith("/emails?error=access_denied")


def test_callback_stores_encrypted_credentials(client, db, user, google_configured, monkeypatch):
    integration = gmail_oauth.get_or_create_integration(db, user.id)
    integration.oauth_state = "state-token-123"
    db.commit()

    credentials = {
        "token": "ya29.access",
        "refresh_token": "1//refresh",
        "token_uri": gmail_oauth.TOKEN_URI,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "scopes": list(settings.GMAIL_SCOPES),
        "expiry": None,
    }
    monkeypatch.setattr(gmail_oauth, "exchange_code", lambda code, state=None: credentials)
    monkeypatch.setattr(gmail_oauth, "fetch_account_email", lambda creds: "candidate@gmail.com")

    response = client.get(
        f"{API}/gmail/callback", params={"code": "auth-code", "state": "state-token-123"}, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == f"{settings.FRONTEND_URL}/emails?connected=1"

    db.expire_all()
    stored = db.scalars(select(EmailIntegration).where(EmailIntegration.user_id == user.id)).first()
    assert stored.status is IntegrationStatus.CONNECTED
    assert stored.email_address == "candidate@gmail.com"
    assert stored.oauth_state is None, "the one-time state must be cleared"
    assert stored.encrypted_credentials and "ya29.access" not in stored.encrypted_credentials
    assert json.loads(decrypt_str(stored.encrypted_credentials))["refresh_token"] == "1//refresh"
    assert "gmail.readonly" in " ".join(stored.scopes)

    actions = {row.action for row in db.scalars(select(AuditLog).where(AuditLog.user_id == user.id))}
    assert "integration.connected" in actions


def test_write_scopes_are_refused():
    with pytest.raises(Exception) as exc:
        gmail_oauth._assert_scopes_are_read_only(["https://www.googleapis.com/auth/gmail.send"])
    assert getattr(exc.value, "code", "") == "invalid_scope"


def test_status_never_leaks_credentials(api, db, user, connected_integration, google_configured):
    body = api.get(API).json()
    assert body["gmail"]["status"] == IntegrationStatus.CONNECTED.value
    assert body["gmail"]["email_address"] == "candidate@gmail.com"
    assert "credentials" not in json.dumps(body)
    assert "refresh-1" not in json.dumps(body)


def test_disconnect_wipes_the_stored_tokens(api, db, user, connected_integration, monkeypatch):
    revoked: list[str] = []
    monkeypatch.setattr(gmail_oauth, "revoke_token", lambda token: revoked.append(token) or True)

    response = api.delete(f"{API}/gmail")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == IntegrationStatus.DISCONNECTED.value

    db.expire_all()
    stored = db.scalars(select(EmailIntegration).where(EmailIntegration.user_id == user.id)).first()
    assert stored.encrypted_credentials is None
    assert stored.scopes == []
    assert stored.status is IntegrationStatus.DISCONNECTED
    assert revoked == ["refresh-1"]

    actions = {row.action for row in db.scalars(select(AuditLog).where(AuditLog.user_id == user.id))}
    assert "integration.disconnected" in actions


def test_disconnect_without_an_integration_is_clean(api):
    response = api.delete(f"{API}/gmail")
    assert response.status_code == 200
    assert response.json()["status"] == IntegrationStatus.DISCONNECTED.value


# --------------------------------------------------------------------------- sync


def test_sync_without_an_integration_fails_cleanly(api):
    response = api.post(f"{API}/gmail/sync")
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "not_connected"


def test_sync_ingests_classifies_and_links(db, user, connected_integration):
    application = make_application(db, user)
    fake = FakeGmail(
        [
            _incoming(
                "Thank you for applying to Acme Cloud",
                "Acme Cloud Careers <no-reply@acmecloud.com>",
                "We have received your application for the Senior Backend Engineer role.",
                "gmail-1",
            ),
            _incoming("Your order has shipped", "ship-confirm@amazon.in", "Arriving tomorrow.", "gmail-2"),
        ]
    )
    result = service.sync_gmail(db, user.id, client=fake)
    db.commit()

    assert result.fetched == 2
    assert result.new == 2
    assert result.classified == 1  # the shipping notice is OTHER
    assert result.linked == 1
    assert result.status_updates == 1

    db.expire_all()
    assert db.get(Application, application.id).status is ApplicationStatus.APPLICATION_RECEIVED
    stored = db.scalars(select(EmailMessage).where(EmailMessage.user_id == user.id)).all()
    assert {row.integration_id for row in stored} == {connected_integration.id}

    # syncing again must not duplicate anything
    again = service.sync_gmail(db, user.id, client=fake)
    db.commit()
    assert again.fetched == 2 and again.new == 0
    assert len(list(db.scalars(select(EmailMessage).where(EmailMessage.user_id == user.id)))) == 2

    db.expire_all()
    integration = db.scalars(select(EmailIntegration).where(EmailIntegration.user_id == user.id)).first()
    assert integration.last_synced_at is not None
    assert integration.last_error is None


def test_sync_reencrypts_refreshed_credentials(db, user, connected_integration):
    fake = FakeGmail([], refreshed=True, credentials={"token": "ya29.refreshed", "refresh_token": "refresh-1"})
    service.sync_gmail(db, user.id, client=fake)
    db.commit()
    db.expire_all()
    integration = db.scalars(select(EmailIntegration).where(EmailIntegration.user_id == user.id)).first()
    assert json.loads(decrypt_str(integration.encrypted_credentials))["token"] == "ya29.refreshed"


def test_sync_failure_is_recorded_on_the_integration(db, user, connected_integration):
    class Broken:
        refreshed = False

        def list_job_related_messages(self, **_kwargs):
            raise RuntimeError("gmail exploded")

    with pytest.raises(RuntimeError):
        service.sync_gmail(db, user.id, client=Broken())

    db.expire_all()
    integration = db.scalars(select(EmailIntegration).where(EmailIntegration.user_id == user.id)).first()
    assert integration.status is IntegrationStatus.ERROR
    assert "gmail exploded" in (integration.last_error or "")


def test_sync_all_connected_never_raises(db, user, connected_integration, monkeypatch):
    class Broken:
        def __init__(self, *_args, **_kwargs) -> None:
            raise RuntimeError("credentials rejected")

    monkeypatch.setattr(service, "GmailClient", Broken)
    results = service.sync_all_connected(db)
    assert list(results) == [str(user.id)]
    assert "credentials rejected" in (results[str(user.id)].error or "")

    db.expire_all()
    integration = db.scalars(select(EmailIntegration).where(EmailIntegration.user_id == user.id)).first()
    assert integration.status is IntegrationStatus.ERROR


def test_sync_all_connected_skips_disabled_integrations(db, user, connected_integration, monkeypatch):
    connected_integration.sync_enabled = False
    db.commit()
    monkeypatch.setattr(service, "GmailClient", lambda *_a, **_k: FakeGmail([]))
    assert service.sync_all_connected(db) == {}


# --------------------------------------------------------------------------- connected accounts


def test_connect_account_encrypts_and_never_returns_credentials(api, db, user):
    payload = {
        "source": "LINKEDIN",
        "account_identifier": "candidate@example.com",
        "credentials": {"username": "candidate@example.com", "password": "hunter2-super-secret"},
    }
    response = api.post(f"{API}/accounts", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["has_credentials"] is True
    assert body["is_mock"] is True
    assert body["status"] == IntegrationStatus.CONNECTED.value
    assert "hunter2-super-secret" not in response.text
    assert "password" not in response.text
    assert "encrypted_credentials" not in body

    db.expire_all()
    account = db.scalars(select(ConnectedAccount).where(ConnectedAccount.user_id == user.id)).first()
    assert account.encrypted_credentials and "hunter2" not in account.encrypted_credentials
    assert json.loads(decrypt_str(account.encrypted_credentials))["password"] == "hunter2-super-secret"

    listing = api.get(f"{API}/accounts")
    assert listing.status_code == 200
    assert "hunter2-super-secret" not in listing.text
    assert listing.json()[0]["has_credentials"] is True

    overview = api.get(API).json()
    linkedin = [a for a in overview["adapters"] if a["source"] == "LINKEDIN"][0]
    assert linkedin["connected"] is True

    actions = {row.action for row in db.scalars(select(AuditLog).where(AuditLog.user_id == user.id))}
    assert "integration.account_connected" in actions


def test_connect_account_is_idempotent_per_source(api, db, user):
    first = api.post(f"{API}/accounts", json={"source": "NAUKRI", "account_identifier": "one@example.com"})
    second = api.post(f"{API}/accounts", json={"source": "NAUKRI", "account_identifier": "two@example.com"})
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["account_identifier"] == "two@example.com"
    assert len(api.get(f"{API}/accounts").json()) == 1


def test_connect_account_with_an_unregistered_source_is_404(api):
    assert api.post(f"{API}/accounts", json={"source": "OTHER"}).status_code == 404


def test_remove_account(api, db, user):
    created = api.post(f"{API}/accounts", json={"source": "INDEED"}).json()
    response = api.delete(f"{API}/accounts/{created['id']}")
    assert response.status_code == 200, response.text
    assert api.get(f"{API}/accounts").json() == []
    actions = {row.action for row in db.scalars(select(AuditLog).where(AuditLog.user_id == user.id))}
    assert "integration.account_removed" in actions


def test_accounts_are_scoped_to_the_current_user(api, db, user):
    other = User(email="other-integrations@example.com", hashed_password=hash_password("StrongPass123!"), full_name="Other")
    db.add(other)
    db.flush()
    foreign = ConnectedAccount(user_id=other.id, source=JobSourceType.LINKEDIN, status=IntegrationStatus.CONNECTED)
    db.add(foreign)
    db.commit()

    assert api.get(f"{API}/accounts").json() == []
    assert api.delete(f"{API}/accounts/{foreign.id}").status_code == 404


def test_connect_account_service_accepts_the_typed_payload(db, user):
    read = service.connect_account(db, user.id, ConnectedAccountCreate(source=JobSourceType.DEMO_ATS))
    db.commit()
    assert read.source is JobSourceType.DEMO_ATS
    assert read.has_credentials is False
    assert read.is_mock is False  # the demo ATS drives a real browser against our own site


def test_sync_all_connected_retries_errored_mailboxes(db, user, connected_integration, monkeypatch):
    """A mailbox left in ERROR by an earlier run is picked up again (failures are usually transient)."""
    connected_integration.status = IntegrationStatus.ERROR
    connected_integration.last_error = "previous failure"
    db.commit()

    def _still_broken(*_args, **_kwargs):
        raise RuntimeError("still broken")

    monkeypatch.setattr(service, "GmailClient", _still_broken)
    results = service.sync_all_connected(db)
    assert list(results) == [str(user.id)]
    assert "still broken" in (results[str(user.id)].error or "")

    db.expire_all()
    integration = db.scalars(select(EmailIntegration).where(EmailIntegration.user_id == user.id)).first()
    assert integration.status is IntegrationStatus.ERROR


def test_sync_all_connected_clears_a_previous_error(db, user, connected_integration, monkeypatch):
    connected_integration.status = IntegrationStatus.ERROR
    connected_integration.last_error = "previous failure"
    db.commit()
    monkeypatch.setattr(service, "GmailClient", lambda *_a, **_k: FakeGmail([]))

    results = service.sync_all_connected(db)
    assert results[str(user.id)].error is None

    db.expire_all()
    integration = db.scalars(select(EmailIntegration).where(EmailIntegration.user_id == user.id)).first()
    assert integration.status is IntegrationStatus.CONNECTED
    assert integration.last_error is None
