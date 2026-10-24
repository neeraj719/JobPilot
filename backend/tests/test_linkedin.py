"""LinkedIn connection: OAuth (state, PKCE, nonce), token storage, sync diff, apply, export
linking, resume creation and the scheduled check — against a fake LinkedIn (httpx.MockTransport).

No test ever reaches linkedin.com: every call goes through ``linkedin_oauth.set_transport``.
"""
from __future__ import annotations

import base64
import hashlib
import io
import time
import uuid
import zipfile
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import select, text

from app.core.config import settings
from app.models.base import utcnow
from app.models.linkedin import LinkedInConnection
from app.models.notification import Notification
from app.models.profile import UserProfile
from app.modules.integrations import linkedin_oauth, linkedin_service

LI = "/api/v1/integrations/linkedin"
CLIENT_ID = "test-linkedin-client"
SUB = "li-member-7f3a"
ACCESS = "AQX-access-token-value-0123456789"
REFRESH = "AQX-refresh-token-value-987654321"

#: The fake LinkedIn's RS256 signing key and its public JWK (served at /oauth/openid/jwks).
SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
KID = "test-kid-1"
PUBLIC_JWK = {**RSAAlgorithm.to_jwk(SIGNING_KEY.public_key(), as_dict=True), "kid": KID, "use": "sig"}

SNAPSHOT = {
    "PROFILE": [
        {
            "First Name": "Asha",
            "Last Name": "Verma",
            "Headline": "Senior Backend Engineer at Nimbus",
            "Summary": "Backend engineer who builds payment and search systems.",
            "Geo Location": "Bengaluru, Karnataka, India",
            "Websites": "[PORTFOLIO:https://asha.dev]",
        }
    ],
    "POSITIONS": [
        {"Company Name": "Nimbus", "Title": "Senior Backend Engineer", "Description": "Owns the payments API.", "Location": "Bengaluru", "Started On": "Mar 2022", "Finished On": ""},
        {"Company Name": "Orbit Labs", "Title": "Backend Engineer", "Description": "Built the search indexer.", "Location": "Pune", "Started On": "Jul 2019", "Finished On": "Feb 2022"},
        {"Company Name": "Quanta Soft", "Title": "Software Engineer", "Description": "", "Location": "Pune", "Started On": "Jun 2017", "Finished On": "Jun 2019"},
    ],
    "EDUCATION": [
        {"School Name": "IIT Bombay", "Degree Name": "M.Tech", "Start Date": "2015", "End Date": "2017"},
        {"School Name": "Pune University", "Degree Name": "B.E.", "Start Date": "2011", "End Date": "2015"},
    ],
    "SKILLS": [{"Name": n} for n in ("Python", "Go", "PostgreSQL", "Redis", "Kafka", "Docker", "Kubernetes", "AWS", "gRPC", "FastAPI", "Terraform", "python")],
    "CERTIFICATIONS": [{"Name": "AWS Certified Solutions Architect", "Authority": "Amazon Web Services", "Started On": "Jan 2023"}],
    "LANGUAGES": [{"Name": "English", "Proficiency": "Full professional proficiency"}, {"Name": "Hindi", "Proficiency": "Native or bilingual proficiency"}],
}


class FakeLinkedIn:
    """Just enough of LinkedIn's OAuth + REST surface for the flow."""

    def __init__(self, *, dma: bool = True, refresh: bool = False) -> None:
        self.dma = dma
        self.refresh = refresh
        self.requests: list[httpx.Request] = []
        self.forms: list[dict[str, list[str]]] = []
        self.nonce: str | None = None
        self.userinfo_status = 200
        self.token_counter = 0
        self.revoked: list[str] = []
        self.name = "Asha Verma"
        #: Answer the code exchange like the real endpoint did for the owner's app.
        self.reject_code = False
        #: Real LinkedIn ID tokens carry no ``nonce`` claim (its discovery document lists none).
        self.include_nonce = False
        self.claims_override: dict[str, Any] = {}
        self.signing_key = SIGNING_KEY
        self.jwks_status = 200

    def id_token(self) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {"iss": "https://www.linkedin.com/oauth", "aud": CLIENT_ID, "sub": SUB, "iat": now, "exp": now + 3600}
        if self.include_nonce:
            claims["nonce"] = self.nonce
        claims.update(self.claims_override)
        return jwt.encode(claims, self.signing_key, algorithm="RS256", headers={"kid": KID})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/oauth/openid/jwks":
            return httpx.Response(self.jwks_status, json={"keys": [PUBLIC_JWK]} if self.jwks_status == 200 else {})
        if path.endswith("/oauth/v2/accessToken"):
            form = parse_qs(request.content.decode())
            self.forms.append(form)
            if self.reject_code and form.get("grant_type") == ["authorization_code"]:
                return httpx.Response(
                    401,
                    json={"error": "invalid_request", "error_description": "Unable to retrieve access token: authorization code not found"},
                )
            self.token_counter += 1
            body: dict[str, Any] = {
                "access_token": ACCESS if self.token_counter == 1 else f"{ACCESS}-{self.token_counter}",
                "expires_in": 5184000,
                "scope": "email,openid,profile" + (",r_dma_portability_3rd_party" if self.dma else ""),
                "token_type": "Bearer",
            }
            if form.get("grant_type") == ["authorization_code"]:
                body["id_token"] = self.id_token()
            if self.refresh:
                body["refresh_token"] = REFRESH
                body["refresh_token_expires_in"] = 31536000
            return httpx.Response(200, json=body)
        if path.endswith("/oauth/v2/revoke"):
            self.revoked.append(parse_qs(request.content.decode())["token"][0])
            return httpx.Response(200, json={})
        if path == "/v2/userinfo":
            if self.userinfo_status != 200:
                return httpx.Response(self.userinfo_status, json={"message": "nope"})
            given, family = self.name.split(" ", 1)
            return httpx.Response(
                200,
                json={
                    "sub": SUB,
                    "name": self.name,
                    "given_name": given,
                    "family_name": family,
                    "email": "asha.verma@example.com",
                    "email_verified": True,
                    "picture": "https://media.licdn.com/dms/image/asha.jpg",
                    "locale": {"country": "IN", "language": "en"},
                },
            )
        if path == "/rest/memberSnapshotData":
            if not self.dma:
                return httpx.Response(403, json={"message": "Not enough permissions"})
            domain = request.url.params["domain"]
            return httpx.Response(200, json={"paging": {"start": 0, "count": 10, "links": []}, "elements": [{"snapshotDomain": domain, "snapshotData": SNAPSHOT.get(domain, [])}]})
        return httpx.Response(404, json={"message": f"unknown {path}"})


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(settings, "LINKEDIN_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(settings, "LINKEDIN_CLIENT_SECRET", "test-linkedin-secret")
    monkeypatch.setattr(settings, "LINKEDIN_DMA_ENABLED", True)
    monkeypatch.setattr(settings, "LINKEDIN_AUTH_BASE", "https://www.linkedin.com/oauth/v2")
    monkeypatch.setattr(settings, "LINKEDIN_API_BASE", "https://api.linkedin.com")
    monkeypatch.setattr(settings, "LINKEDIN_REDIRECT_URI", "http://testserver/api/v1/integrations/linkedin/callback")
    # The owner's root .env may set this; the suite pins the shipped default.
    monkeypatch.setattr(settings, "LINKEDIN_PKCE_ENABLED", False)
    linkedin_oauth._JWKS_CACHE.clear()
    fake_li = FakeLinkedIn()
    linkedin_oauth.set_transport(httpx.MockTransport(fake_li))
    yield fake_li
    linkedin_oauth.set_transport(None)
    linkedin_oauth._JWKS_CACHE.clear()


def _user_id(client) -> uuid.UUID:
    return uuid.UUID(client.get("/api/v1/auth/me").json()["id"])


def _start(client, fake_li: FakeLinkedIn) -> dict[str, str]:
    r = client.post(f"{LI}/connect")
    assert r.status_code == 200, r.text
    query = {k: v[0] for k, v in parse_qs(urlparse(r.json()["authorization_url"]).query).items()}
    fake_li.nonce = query["nonce"]
    return query


def _callback(client, state: str, code: str = "auth-code-1", **extra) -> httpx.Response:
    return client.get(f"{LI}/callback", params={"code": code, "state": state, **extra}, follow_redirects=False)


def _connect(client, fake_li: FakeLinkedIn) -> dict[str, str]:
    query = _start(client, fake_li)
    r = _callback(client, query["state"])
    assert r.status_code == 302 and r.headers["location"].endswith("/resume/new?source=linkedin&connected=1"), r.headers.get("location")
    return query


def _error_of(response: httpx.Response) -> str:
    return parse_qs(urlparse(response.headers["location"]).query).get("error", [""])[0]


def _connection(db, user_id) -> LinkedInConnection:
    db.expire_all()
    return db.scalars(select(LinkedInConnection).where(LinkedInConnection.user_id == user_id)).one()


# --------------------------------------------------------------------------- connect


def test_status_when_not_configured(auth_client, monkeypatch):
    monkeypatch.setattr(settings, "LINKEDIN_CLIENT_ID", None)  # the root .env may configure a real app
    body = auth_client.get(LI).json()
    assert body["configured"] is False and body["status"] == "not_connected"
    r = auth_client.post(f"{LI}/connect")
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_configured"


def test_pkce_is_off_by_default(auth_client, fake):
    """LinkedIn's web flow rejected codes issued with a code_challenge (owner's app, 2026-10-24)."""
    from app.core.config import Settings

    assert Settings.model_fields["LINKEDIN_PKCE_ENABLED"].default is False
    query = _connect(auth_client, fake)
    assert "code_challenge" not in query and "code_challenge_method" not in query
    assert "code_verifier" not in fake.forms[0]


def test_connect_url_has_pkce_state_and_scopes(auth_client, db, fake, monkeypatch):
    monkeypatch.setattr(settings, "LINKEDIN_PKCE_ENABLED", True)
    query = _start(auth_client, fake)
    assert query["response_type"] == "code" and query["client_id"] == CLIENT_ID
    assert query["scope"].split() == ["openid", "profile", "email", "r_dma_portability_3rd_party"]
    assert query["code_challenge_method"] == "S256" and len(query["code_challenge"]) == 43
    payload = jwt.decode(query["state"], settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    assert payload["sub"] == str(_user_id(auth_client)) and payload["exp"] - payload["iat"] == 600
    row = _connection(db, _user_id(auth_client))
    assert row.oauth_state == payload["jti"] and row.encrypted_oauth_pending and row.status == "pending"
    assert query["nonce"] not in row.encrypted_oauth_pending
    assert auth_client.cookies.get(linkedin_oauth.STATE_COOKIE_NAME) == query["state"]


def test_callback_happy_path_sends_verifier_and_encrypts_tokens(auth_client, db, fake, monkeypatch):
    monkeypatch.setattr(settings, "LINKEDIN_PKCE_ENABLED", True)
    fake.refresh = True
    query = _connect(auth_client, fake)
    form = fake.forms[0]
    verifier = form["code_verifier"][0]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == query["code_challenge"]
    assert form["grant_type"] == ["authorization_code"] and form["client_id"] == [CLIENT_ID]

    user_id = _user_id(auth_client)
    row = _connection(db, user_id)
    assert row.status == "connected" and row.subject == SUB and row.name == "Asha Verma"
    assert row.locale == "en_IN" and "r_dma_portability_3rd_party" in row.scopes
    assert row.oauth_state is None and row.encrypted_oauth_pending is None  # single use
    raw = db.execute(text('SELECT row_to_json(c)::text FROM "master"."linkedin_connections" c')).scalar_one()
    assert ACCESS not in raw and REFRESH not in raw and row.encrypted_access_token and row.encrypted_refresh_token

    status = auth_client.get(LI)
    assert status.status_code == 200
    body = status.json()
    assert body["connected"] is True and body["email"] == "asha.verma@example.com" and body["dma_granted"] is True
    assert ACCESS not in status.text and REFRESH not in status.text
    assert not any("token" in key and key != "token_expires_at" for key in body)
    assert "encrypted" not in status.text and "oauth_state" not in status.text


def test_state_reuse_is_rejected(auth_client, fake):
    query = _connect(auth_client, fake)
    auth_client.cookies.set(linkedin_oauth.STATE_COOKIE_NAME, query["state"], path=f"{settings.API_PREFIX}/integrations/linkedin")
    replay = _callback(auth_client, query["state"], code="auth-code-2")
    assert _error_of(replay) == "invalid_state"
    assert len(fake.forms) == 1  # no second token exchange


def test_a_newer_start_supersedes_the_older_flow(auth_client, db, fake, monkeypatch):
    """Two connect starts (two consent tabs): the second state completes; the first never
    reaches LinkedIn's token endpoint. One live row per user, resolved by the state's jti."""
    monkeypatch.setattr(settings, "LINKEDIN_PKCE_ENABLED", True)
    first = _start(auth_client, fake)
    second = _start(auth_client, fake)  # fake.nonce now belongs to the second flow
    assert first["state"] != second["state"] and first["code_challenge"] != second["code_challenge"]
    rows = db.execute(text('SELECT count(*) FROM "master"."linkedin_connections" WHERE deleted_at IS NULL')).scalar_one()
    assert rows == 1

    r = _callback(auth_client, second["state"])
    assert r.headers["location"].endswith("connected=1"), r.headers["location"]
    verifier = fake.forms[0]["code_verifier"][0]
    assert base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode() == second["code_challenge"]

    auth_client.cookies.set(linkedin_oauth.STATE_COOKIE_NAME, first["state"], path=f"{settings.API_PREFIX}/integrations/linkedin")
    assert _error_of(_callback(auth_client, first["state"], code="old-tab-code")) == "invalid_state"
    assert len(fake.forms) == 1


def test_older_tab_finishing_after_a_newer_start_is_rejected_without_an_exchange(auth_client, fake):
    first = _start(auth_client, fake)
    _start(auth_client, fake)
    auth_client.cookies.set(linkedin_oauth.STATE_COOKIE_NAME, first["state"], path=f"{settings.API_PREFIX}/integrations/linkedin")
    assert _error_of(_callback(auth_client, first["state"])) == "invalid_state"
    assert fake.forms == []


def test_code_rejected_by_linkedin_is_reported_specifically(auth_client, db, fake, caplog):
    fake.reject_code = True
    query = _start(auth_client, fake)
    with caplog.at_level("WARNING"):
        r = _callback(auth_client, query["state"], code="the-auth-code-123")
    assert _error_of(r) == "linkedin_code_rejected"
    logged = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "authorization code not found" in logged and "invalid_request" in logged
    assert "the-auth-code-123" not in logged and "test-linkedin-secret" not in logged
    row = _connection(db, _user_id(auth_client))
    assert row.oauth_state is None and row.encrypted_access_token is None  # burnt: no retry with this state
    assert "do not reuse an old tab" in (row.last_error or "")
    failed = db.execute(
        text("SELECT metadata::text FROM audit.audit_logs WHERE action = 'integration.linkedin.connect_failed'")
    ).scalar_one()
    assert "linkedin_code_rejected" in failed and "the-auth-code-123" not in failed


def test_token_error_details_strip_sent_values():
    response = httpx.Response(401, json={"error": "invalid_request", "error_description": "code abc-secret-code not found for s3cr3t-value"})
    error, description = linkedin_oauth.token_error_details(response, {"code": "abc-secret-code", "client_secret": "s3cr3t-value"})
    assert error == "invalid_request" and "abc-secret-code" not in description and "s3cr3t-value" not in description


def test_tampered_or_foreign_state_is_rejected(auth_client, fake):
    query = _start(auth_client, fake)
    head, body, sig = query["state"].split(".")
    tampered = f"{head}.{body}.{sig[:-2]}{'AA' if sig[-2:] != 'AA' else 'BB'}"
    assert _error_of(_callback(auth_client, tampered)) == "invalid_state"
    forged = jwt.encode({"sub": str(_user_id(auth_client)), "type": "linkedin_oauth_state", "jti": "x", "exp": int(time.time()) + 60}, "another-key-0123456789abcdef0123456789", algorithm="HS256")
    assert _error_of(_callback(auth_client, forged)) == "invalid_state"
    assert fake.forms == []


def test_expired_state_is_rejected(auth_client, db, fake, monkeypatch):
    monkeypatch.setattr(linkedin_oauth, "STATE_TTL_SECONDS", -5)
    query = _start(auth_client, fake)
    auth_client.cookies.set(linkedin_oauth.STATE_COOKIE_NAME, query["state"], path=f"{settings.API_PREFIX}/integrations/linkedin")
    assert _error_of(_callback(auth_client, query["state"])) == "state_expired"
    assert _connection(db, _user_id(auth_client)).oauth_state is None
    assert fake.forms == []


def test_callback_without_the_browser_cookie_is_rejected_and_burns_the_state(auth_client, db, fake):
    query = _start(auth_client, fake)
    auth_client.cookies.clear()
    r = auth_client.get(f"{LI}/callback", params={"code": "c", "state": query["state"]}, follow_redirects=False)
    assert _error_of(r) == "state_mismatch"
    assert _connection(db, _user_id(auth_client)).oauth_state is None


def test_nonce_mismatch_is_rejected(auth_client, db, fake):
    query = _start(auth_client, fake)
    fake.include_nonce = True
    fake.nonce = "someone-elses-nonce"
    assert _error_of(_callback(auth_client, query["state"])) == "nonce_mismatch"
    assert _connection(db, _user_id(auth_client)).encrypted_access_token is None


def test_id_token_without_nonce_is_accepted_once_the_state_matched(auth_client, db, fake, caplog):
    """LinkedIn's ID token has no nonce claim (live finding); the signed single-use state binds it."""
    assert fake.include_nonce is False
    with caplog.at_level("INFO"):
        _connect(auth_client, fake)
    assert _connection(db, _user_id(auth_client)).status == "connected"
    assert any("without nonce claim" in rec.getMessage() for rec in caplog.records)


def test_matching_nonce_is_accepted(auth_client, db, fake):
    fake.include_nonce = True
    _connect(auth_client, fake)
    assert _connection(db, _user_id(auth_client)).status == "connected"


def test_id_token_for_another_app_is_rejected(auth_client, db, fake):
    query = _start(auth_client, fake)
    fake.claims_override = {"aud": "someone-elses-client"}
    assert _error_of(_callback(auth_client, query["state"])) == "id_token_invalid"
    assert _connection(db, _user_id(auth_client)).encrypted_access_token is None


def test_id_token_signed_with_another_key_is_rejected(auth_client, db, fake):
    query = _start(auth_client, fake)
    fake.signing_key = OTHER_KEY
    assert _error_of(_callback(auth_client, query["state"])) == "id_token_invalid"
    assert _connection(db, _user_id(auth_client)).encrypted_access_token is None


def test_id_token_signature_is_checked_against_the_jwks():
    linkedin_oauth._JWKS_CACHE.clear()
    fake_li = FakeLinkedIn()
    linkedin_oauth.set_transport(httpx.MockTransport(fake_li))
    try:
        good = fake_li.id_token()
        assert linkedin_oauth._verify_signature(good) is True
        fake_li.signing_key = OTHER_KEY
        with pytest.raises(Exception) as caught:
            linkedin_oauth._verify_signature(fake_li.id_token())
        assert getattr(caught.value, "code", None) == "id_token_invalid"
        hs = jwt.encode({"sub": SUB}, "shared-secret-0123456789abcdef0123", algorithm="HS256")
        with pytest.raises(Exception) as caught:
            linkedin_oauth._verify_signature(hs)
        assert getattr(caught.value, "code", None) == "id_token_invalid"  # HS*/none never accepted
        jwks_calls = [r for r in fake_li.requests if r.url.path == "/oauth/openid/jwks"]
        assert len(jwks_calls) == 1  # cached
    finally:
        linkedin_oauth.set_transport(None)
        linkedin_oauth._JWKS_CACHE.clear()


def test_jwks_unreachable_falls_back_to_userinfo(auth_client, db, fake):
    fake.jwks_status = 503
    fake.claims_override = {"sub": "someone-else"}  # unverified claims are not trusted over userinfo
    _connect(auth_client, fake)
    row = _connection(db, _user_id(auth_client))
    assert row.status == "connected" and row.subject == SUB


def test_member_cancelling_consent_lands_back_with_access_denied(client):
    r = client.get(f"{LI}/callback", params={"error": "user_cancelled_authorize", "state": "x"}, follow_redirects=False)
    assert r.status_code == 302 and _error_of(r) == "access_denied"


# --------------------------------------------------------------------------- sync / diff / apply


def test_sync_against_an_empty_profile_proposes_additions_only_and_writes_nothing(auth_client, db, fake):
    _connect(auth_client, fake)
    r = auth_client.post(f"{LI}/sync")
    assert r.status_code == 200, r.text
    diff = r.json()["diff"]
    assert diff["history_source"] == "dma"
    rows = {row["id"]: row for row in diff["rows"]}
    assert rows["headline"]["action"] == "add" and rows["headline"]["default_selected"] is True
    experience = [row for row in diff["rows"] if row["field"] == "previous_companies"]
    assert len(experience) == 3 and all(row["action"] == "add" for row in experience)
    skills = [row for row in diff["rows"] if row["field"] == "skills"]
    assert len(skills) == 11  # "python" twice is one skill
    profile = db.scalars(select(UserProfile).where(UserProfile.user_id == _user_id(auth_client))).first()
    assert profile is None or (not profile.headline and not profile.previous_companies)
    assert r.json()["status"]["pending_changes"] == diff["changes"]


def test_conflicts_stay_unticked_and_apply_respects_them(auth_client, db, fake):
    auth_client.put("/api/v1/profile", json={"headline": "Backend developer", "skills": ["Python", "Docker"]})
    _connect(auth_client, fake)
    diff = auth_client.post(f"{LI}/sync").json()["diff"]
    rows = {row["id"]: row for row in diff["rows"]}
    assert rows["headline"]["action"] == "replace" and rows["headline"]["default_selected"] is False
    assert rows["skills:python"]["action"] == "same" and rows["skills:docker"]["action"] == "same"

    ticked = [row["id"] for row in diff["rows"] if row["default_selected"]]
    applied = auth_client.post(f"{LI}/apply", json={"change_ids": ticked}).json()
    assert applied["applied"] == len(ticked)
    db.expire_all()
    profile = db.scalars(select(UserProfile).where(UserProfile.user_id == _user_id(auth_client))).one()
    assert profile.headline == "Backend developer"  # the unticked conflict was not written
    assert [s.lower() for s in profile.skills].count("python") == 1 and "Kafka" in profile.skills
    assert len(profile.previous_companies) == 3 and profile.current_company == "Nimbus"

    again = auth_client.post(f"{LI}/apply", json={"change_ids": ["headline"]}).json()
    assert again["applied"] == 1
    # left: the account name and email the profile started with, which disagree with LinkedIn
    assert sorted(r["id"] for r in again["diff"]["rows"] if r["action"] != "same") == ["email", "full_name"]
    db.expire_all()
    assert db.scalars(select(UserProfile).where(UserProfile.user_id == _user_id(auth_client))).one().headline == "Senior Backend Engineer at Nimbus"


def test_list_merge_updates_matching_entries_in_place(auth_client, db, fake):
    auth_client.put(
        "/api/v1/profile",
        json={"previous_companies": [{"company": "Orbit Labs", "title": "Backend Engineer", "start": "2019-07", "end": "2021-12"}]},
    )
    _connect(auth_client, fake)
    diff = auth_client.post(f"{LI}/sync").json()["diff"]
    orbit = next(row for row in diff["rows"] if row["id"] == "previous_companies:orbit labs|backend engineer")
    assert orbit["action"] == "replace" and orbit["default_selected"] is False
    assert orbit["incoming"]["end"] == "2022-02" and orbit["current"]["end"] == "2021-12"
    auth_client.post(f"{LI}/apply", json={"change_ids": [orbit["id"]]})
    db.expire_all()
    companies = db.scalars(select(UserProfile).where(UserProfile.user_id == _user_id(auth_client))).one().previous_companies
    assert len(companies) == 1 and companies[0]["end"] == "2022-02" and companies[0]["description"] == "Built the search indexer."


def test_apply_ignores_ids_it_did_not_propose(auth_client, fake):
    _connect(auth_client, fake)
    auth_client.post(f"{LI}/sync")
    r = auth_client.post(f"{LI}/apply", json={"change_ids": ["hashed_password", "skills:made-up"]})
    assert r.status_code == 200 and r.json()["applied"] == 0 and sorted(r.json()["skipped"]) == ["hashed_password", "skills:made-up"]


def test_oidc_only_degrades_to_basics(auth_client, db, fake):
    fake.dma = False
    _connect(auth_client, fake)
    body = auth_client.post(f"{LI}/sync").json()
    assert body["diff"]["history_source"] is None
    assert {row["field"] for row in body["diff"]["rows"]} <= {"full_name", "first_name", "last_name", "email"}
    assert any("export" in note for note in body["notes"])
    assert body["status"]["dma_granted"] is False


def test_expired_token_without_refresh_asks_to_reconnect(auth_client, db, fake):
    _connect(auth_client, fake)
    user_id = _user_id(auth_client)
    row = _connection(db, user_id)
    row.token_expires_at = utcnow() - timedelta(days=1)
    db.commit()
    r = auth_client.post(f"{LI}/sync")
    assert r.status_code == 422 and r.json()["error"]["code"] == "reconnect_required"
    assert _connection(db, user_id).status == "expired"


def test_expired_token_is_refreshed_when_linkedin_gave_a_refresh_token(auth_client, db, fake):
    fake.refresh = True
    _connect(auth_client, fake)
    user_id = _user_id(auth_client)
    row = _connection(db, user_id)
    row.token_expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    assert auth_client.post(f"{LI}/sync").status_code == 200
    assert fake.forms[-1]["grant_type"] == ["refresh_token"] and fake.forms[-1]["refresh_token"] == [REFRESH]
    assert _connection(db, user_id).token_expires_at > utcnow()


def test_a_revoked_app_is_marked_revoked(auth_client, db, fake):
    _connect(auth_client, fake)
    fake.userinfo_status = 401
    r = auth_client.post(f"{LI}/sync")
    assert r.status_code == 422 and r.json()["error"]["code"] == "reconnect_required"
    row = _connection(db, _user_id(auth_client))
    assert row.status == "revoked" and row.encrypted_access_token is None


def test_disconnect_revokes_wipes_and_soft_deletes(auth_client, db, fake):
    _connect(auth_client, fake)
    auth_client.post(f"{LI}/sync")
    r = auth_client.delete(LI)
    assert r.status_code == 200 and r.json()["status"] == "not_connected"
    assert fake.revoked == [ACCESS]
    raw = db.execute(
        text('SELECT deleted_at, encrypted_access_token, profile_snapshot::text FROM "master"."linkedin_connections"')
    ).one()
    assert raw[0] is not None and raw[1] is None and raw[2] == "{}"
    assert auth_client.post(f"{LI}/sync").json()["error"]["code"] == "not_connected"


def test_auto_sync_toggle(auth_client, fake):
    _connect(auth_client, fake)
    assert auth_client.patch(LI, json={"auto_sync": False}).json()["auto_sync"] is False
    assert auth_client.get(LI).json()["auto_sync"] is False


def test_endpoints_are_per_user(auth_client, client, fake):
    _connect(auth_client, fake)
    other = client.post("/api/v1/auth/register", json={"email": "other@example.com", "password": "StrongPass123!", "full_name": "Other"})
    headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert client.get(LI, headers=headers).json()["status"] == "not_connected"


# --------------------------------------------------------------------------- DMA mapping + resume


def test_dma_snapshot_maps_like_the_export():
    parsed = linkedin_service.parse_snapshot_domains(SNAPSHOT)
    assert [e.company for e in parsed.experience] == ["Nimbus", "Orbit Labs", "Quanta Soft"]
    assert parsed.experience[0].start == "2022-03" and parsed.experience[0].end == "Present"
    assert parsed.experience[1].end == "2022-02"
    assert [e.institution for e in parsed.education] == ["IIT Bombay", "Pune University"]
    assert len(parsed.skills) == 11 and parsed.certifications[0].year == "2023"
    assert parsed.name == "Asha Verma" and parsed.links.portfolio == "https://asha.dev"


def test_from_linkedin_creates_a_system_version(auth_client, fake):
    _connect(auth_client, fake)
    auth_client.post(f"{LI}/sync")
    r = auth_client.post("/api/v1/resumes/from-linkedin", json={})
    assert r.status_code == 201, r.text
    resume = r.json()
    assert len(resume["parsed_data"]["experience"]) == 3 and resume["parsed_data"]["email"] == "asha.verma@example.com"
    versions = auth_client.get(f"/api/v1/resumes/{resume['id']}/versions").json()
    assert versions[0]["change_source"] == "SYSTEM" and versions[0]["note"] == "Imported from LinkedIn"


def test_from_linkedin_with_basics_only_uses_the_profile(auth_client, fake):
    fake.dma = False
    auth_client.put("/api/v1/profile", json={"previous_companies": [{"company": "Acme", "title": "Engineer"}]})
    _connect(auth_client, fake)
    auth_client.post(f"{LI}/sync")
    resume = auth_client.post("/api/v1/resumes/from-linkedin", json={}).json()
    assert [e["company"] for e in resume["parsed_data"]["experience"]] == ["Acme"]


def test_from_linkedin_requires_a_connection(auth_client):
    r = auth_client.post("/api/v1/resumes/from-linkedin", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_connected"


def _export_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("Profile.csv", "First Name,Last Name,Headline\nAsha,Verma,Engineer\n")
        archive.writestr("Positions.csv", "Company Name,Title,Description,Location,Started On,Finished On\nNimbus,Engineer,,Pune,Mar 2022,\n")
    return buf.getvalue()


def test_export_uploaded_while_connected_is_linked(auth_client, db, fake):
    fake.dma = False
    _connect(auth_client, fake)
    r = auth_client.post("/api/v1/resumes/import/linkedin", files={"files": ("export.zip", _export_zip(), "application/zip")})
    assert r.status_code == 201, r.text
    row = _connection(db, _user_id(auth_client))
    assert row.export_imported_at is not None and row.snapshot_source == "export"
    status = auth_client.get(LI).json()
    assert status["history_source"] == "export" and status["history_counts"]["positions"] == 1


def test_add_export_endpoint_returns_a_diff(auth_client, fake):
    fake.dma = False
    _connect(auth_client, fake)
    r = auth_client.post(f"{LI}/export", files={"files": ("export.zip", _export_zip(), "application/zip")})
    assert r.status_code == 200, r.text
    assert any(row["field"] == "previous_companies" for row in r.json()["diff"]["rows"])


# --------------------------------------------------------------------------- scheduler


def test_scheduled_check_notifies_once_and_never_writes(auth_client, db, fake):
    _connect(auth_client, fake)
    user_id = _user_id(auth_client)
    results = linkedin_service.sync_due_connections(db)
    assert results[str(user_id)].startswith("synced:") and results[str(user_id)].endswith(":notified")
    notes = db.scalars(select(Notification).where(Notification.user_id == user_id)).all()
    assert len(notes) == 1 and notes[0].title.startswith("LinkedIn: ") and notes[0].link == linkedin_service.REVIEW_LINK
    profile = db.scalars(select(UserProfile).where(UserProfile.user_id == user_id)).first()
    assert profile is None or not profile.previous_companies

    later = utcnow() + timedelta(hours=settings.LINKEDIN_AUTO_SYNC_HOURS + 1)
    again = linkedin_service.sync_due_connections(db, later)
    assert not again[str(user_id)].endswith(":notified")  # same changes, no second notification
    db.expire_all()
    assert len(db.scalars(select(Notification).where(Notification.user_id == user_id)).all()) == 1
    assert linkedin_service.sync_due_connections(db) == {}  # just synced: not due


def test_scheduled_check_skips_users_without_resume_studio(auth_client, db, fake):
    _connect(auth_client, fake)
    db.execute(text("UPDATE \"master\".\"modules\" SET is_enabled = false WHERE code = 'resume'"))
    db.commit()
    assert linkedin_service.sync_due_connections(db) == {str(_user_id(auth_client)): "skipped_module"}
    calls = [r.url.path for r in fake.requests if r.url.path != "/oauth/openid/jwks"]
    assert len(calls) == 2  # token + userinfo from the connect, nothing from the job


def test_scheduled_check_skips_auto_sync_off(auth_client, db, fake):
    _connect(auth_client, fake)
    auth_client.patch(LI, json={"auto_sync": False})
    assert linkedin_service.sync_due_connections(db) == {}
