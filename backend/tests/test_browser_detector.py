"""Form detection rules (CONTRACTS.md section 12).

Most tests run the browser-free ``detect_form_from_html`` against the markup the demo ATS
really serves. The ``browser`` marked tests additionally drive Chromium and assert the
two detectors agree; they skip when ``playwright install chromium`` has not been run.
"""
from __future__ import annotations

import re
import socket
import threading
import time
import uuid
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.demo_ats.router import router as demo_ats_router
from app.models.enums import FieldType, JobSourceType, PauseReason
from app.modules.browser.detector import detect_form, detect_form_from_html

SLUG = "northwind-labs-full-stack-engineer"
EXPECTED_NAMES = [
    "first_name",
    "last_name",
    "email",
    "phone",
    "location",
    "linkedin",
    "github",
    "portfolio",
    "resume",
    "total_experience",
    "react_experience",
    "current_ctc",
    "expected_ctc",
    "notice_period",
    "work_authorization",
    "why_company",
    "start_date",
    "consent",
]


def build_demo_app() -> FastAPI:
    """Just the demo ATS - detection is about markup, not about the rest of the API."""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(demo_ats_router, prefix="/demo-ats")
    return app


@pytest.fixture(scope="module")
def demo_client() -> TestClient:
    with TestClient(build_demo_app()) as client:
        yield client


@pytest.fixture(scope="module")
def apply_html(demo_client: TestClient) -> str:
    response = demo_client.get(f"/demo-ats/jobs/{SLUG}/apply")
    assert response.status_code == 200
    return response.text


# --------------------------------------------------------------------------- demo ATS form


def test_detects_every_field_of_the_demo_apply_form(apply_html: str) -> None:
    form = detect_form_from_html(apply_html, url=f"http://demo/demo-ats/jobs/{SLUG}/apply")
    assert [f.name for f in form.fields] == EXPECTED_NAMES
    assert all(f.selector for f in form.fields)
    types = {f.name: f.field_type for f in form.fields}
    assert types["email"] is FieldType.EMAIL
    assert types["phone"] is FieldType.PHONE
    assert types["resume"] is FieldType.FILE
    assert types["total_experience"] is FieldType.NUMBER
    assert types["linkedin"] is FieldType.URL
    assert types["notice_period"] is FieldType.SELECT
    assert types["work_authorization"] is FieldType.RADIO
    assert types["why_company"] is FieldType.TEXTAREA
    assert types["consent"] is FieldType.CHECKBOX


def test_required_flags_match_the_form(apply_html: str) -> None:
    required = {f.name: f.required for f in detect_form_from_html(apply_html).fields}
    for name in ("first_name", "email", "resume", "expected_ctc", "notice_period", "work_authorization", "consent"):
        assert required[name] is True, name
    for name in ("linkedin", "github", "portfolio", "current_ctc"):
        assert required[name] is False, name


def test_labels_come_from_the_label_elements(apply_html: str) -> None:
    labels = {f.name: f.label for f in detect_form_from_html(apply_html).fields}
    assert labels["first_name"] == "First Name *"
    assert labels["react_experience"] == "Years of experience with React *"
    assert labels["work_authorization"] == "Are you legally authorized to work in India? *"
    assert labels["why_company"].startswith("Why do you want to work at Northwind Labs?")


def test_radio_group_becomes_one_field_with_options(apply_html: str) -> None:
    form = detect_form_from_html(apply_html)
    radios = [f for f in form.fields if f.field_type is FieldType.RADIO]
    assert len(radios) == 1
    group = radios[0]
    assert group.selector == 'input[type="radio"][name="work_authorization"]'
    assert [o.label for o in group.options] == ["Yes", "No"]
    assert [o.value for o in group.options] == ["Yes", "No"]
    assert [o.selector for o in group.options] == ["#work_authorization_yes", "#work_authorization_no"]


def test_select_options_drop_the_placeholder(apply_html: str) -> None:
    select = next(f for f in detect_form_from_html(apply_html).fields if f.name == "notice_period")
    assert [o.label for o in select.options] == ["Immediate", "15 days", "30 days", "60 days", "90 days"]


def test_submit_selector_is_found(apply_html: str) -> None:
    assert detect_form_from_html(apply_html).submit_selector == 'button[type="submit"]'


def test_plain_apply_form_has_no_blockers(apply_html: str) -> None:
    assert detect_form_from_html(apply_html).blockers == []


def test_captcha_query_flag_produces_a_captcha_blocker(demo_client: TestClient) -> None:
    html = demo_client.get(f"/demo-ats/jobs/{SLUG}/apply?captcha=1").text
    form = detect_form_from_html(html)
    assert len(form.blockers) == 1
    blocker = form.blockers[0]
    assert blocker.kind is PauseReason.CAPTCHA
    assert blocker.selector == ".g-recaptcha"
    assert "never solves" in blocker.message
    # the widget must not swallow the rest of the form
    assert [f.name for f in form.fields] == EXPECTED_NAMES


# --------------------------------------------------------------------------- generic rules


def test_label_resolution_order() -> None:
    html = """
    <html><body><form>
      <div><label for="a">Aye</label><input id="a" name="a"></div>
      <div><input id="b" name="b" aria-label="Bee"></div>
      <div><span id="clabel">Cee</span><input id="c" name="c" aria-labelledby="clabel"></div>
      <div><label>Dee <input id="d" name="d"></label></div>
      <div><input id="e" name="e" placeholder="Eee"></div>
      <div><p>Eff</p><input id="f" name="f"></div>
      <div><input id="g" name="g"></div>
    </form></body></html>
    """
    labels = {f.name: f.label for f in detect_form_from_html(html).fields}
    assert labels == {"a": "Aye", "b": "Bee", "c": "Cee", "d": "Dee", "e": "Eee", "f": "Eff", "g": "g"}


def test_selector_prefers_id_then_name_then_path() -> None:
    html = """
    <html><body><form>
      <div><input id="with_id" name="n1"></div>
      <div><input name="n2"></div>
      <div><input></div>
    </form></body></html>
    """
    selectors = [f.selector for f in detect_form_from_html(html).fields]
    assert selectors[0] == "#with_id"
    assert selectors[1] == 'input[name="n2"]'
    assert "nth-of-type" in selectors[2]


def test_hidden_submit_and_button_controls_are_skipped() -> None:
    html = """
    <html><body><form>
      <input type="hidden" name="csrf" value="x">
      <input type="text" name="visible">
      <input type="text" name="inline_hidden" style="display:none">
      <input type="text" name="attr_hidden" hidden>
      <input type="submit" value="Go">
      <button type="button">Cancel</button>
      <button type="submit">Submit Application</button>
    </form></body></html>
    """
    form = detect_form_from_html(html)
    assert [f.name for f in form.fields] == ["visible"]
    assert form.submit_selector is not None


def test_required_detected_from_aria_required_and_asterisk() -> None:
    html = """
    <html><body><form>
      <div><label for="a">Aye <span>*</span></label><input id="a" name="a"></div>
      <div><label for="b">Bee</label><input id="b" name="b" aria-required="true"></div>
      <div><label for="c">Cee</label><input id="c" name="c"></div>
    </form></body></html>
    """
    required = {f.name: f.required for f in detect_form_from_html(html).fields}
    assert required == {"a": True, "b": True, "c": False}


def test_otp_field_is_a_blocker() -> None:
    html = """
    <html><body><h1>Verify it is you</h1><form>
      <label for="otp">Enter the OTP sent to your phone</label>
      <input id="otp" name="otp" autocomplete="one-time-code">
      <button type="submit">Verify</button>
    </form></body></html>
    """
    kinds = [b.kind for b in detect_form_from_html(html).blockers]
    assert PauseReason.OTP in kinds


def test_login_wall_is_a_blocker() -> None:
    html = """
    <html><body><h1>Sign in to continue</h1><form>
      <label for="u">Email</label><input id="u" name="username" type="email">
      <label for="p">Password</label><input id="p" name="password" type="password">
      <button type="submit">Log in</button>
    </form></body></html>
    """
    blockers = detect_form_from_html(html).blockers
    assert [b.kind for b in blockers] == [PauseReason.LOGIN_REQUIRED]
    assert blockers[0].selector == "#p"


def test_account_registration_prompt_is_a_blocker() -> None:
    html = """
    <html><body><h2>Create an account to apply</h2><form>
      <label for="e">Email</label><input id="e" name="email" type="email">
      <label for="p1">Password</label><input id="p1" name="password" type="password">
      <label for="p2">Confirm Password</label><input id="p2" name="confirm_password" type="password">
      <button type="submit">Register</button>
    </form></body></html>
    """
    kinds = [b.kind for b in detect_form_from_html(html).blockers]
    assert kinds == [PauseReason.ACCOUNT_REGISTRATION_REQUIRED]


def test_a_real_application_form_behind_a_password_is_not_a_login_wall(apply_html: str) -> None:
    html = apply_html.replace(
        '<button type="submit">Submit Application</button>',
        '<label for="pw">Password</label><input id="pw" name="password" type="password">'
        '<button type="submit">Submit Application</button>',
    )
    assert detect_form_from_html(html).blockers == []


# --------------------------------------------------------------------------- live browser


@dataclass
class _Answer:
    """Duck-typed stand-in for ApplicationAnswer (the applications module owns the real one)."""

    question_key: str
    answer: str
    status: str = "ANSWERED"
    field_selector: str | None = None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def live_server() -> str:
    """Serve the demo ATS from a background uvicorn thread so Chromium can reach it."""
    import uvicorn

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(build_demo_app(), host="127.0.0.1", port=port, log_level="warning", lifespan="off")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 30
    while not server.started and thread.is_alive() and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:  # pragma: no cover - CI safety net
        pytest.skip("uvicorn did not start in time")
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=15)


@pytest.fixture
def browser_session(live_server: str):
    from app.modules.browser.session import BrowserSessionHandle, is_browser_available

    if not is_browser_available():
        pytest.skip("Chromium is not installed - run: python -m playwright install chromium")
    with BrowserSessionHandle(uuid.uuid4(), JobSourceType.DEMO_ATS, None) as handle:
        yield handle


@pytest.mark.browser
def test_live_detection_matches_the_html_detector(live_server: str, browser_session) -> None:
    url = f"{live_server}/demo-ats/jobs/{SLUG}/apply"
    browser_session.page.goto(url)
    live = detect_form(browser_session.page)
    offline = detect_form_from_html(browser_session.page.content(), url=url)

    assert live.url == url
    assert live.submit_selector == offline.submit_selector == 'button[type="submit"]'
    assert [f.name for f in live.fields] == EXPECTED_NAMES
    for a, b in zip(live.fields, offline.fields, strict=True):
        assert (a.selector, a.name, a.label, a.field_type, a.required) == (b.selector, b.name, b.label, b.field_type, b.required)
        assert [(o.value, o.label, o.selector) for o in a.options] == [(o.value, o.label, o.selector) for o in b.options]
    assert live.blockers == offline.blockers == []


@pytest.mark.browser
def test_live_captcha_widget_is_detected(live_server: str, browser_session) -> None:
    browser_session.page.goto(f"{live_server}/demo-ats/jobs/{SLUG}/apply?captcha=1")
    form = detect_form(browser_session.page)
    assert [b.kind for b in form.blockers] == [PauseReason.CAPTCHA]
    assert len(form.fields) == len(EXPECTED_NAMES)


@pytest.mark.browser
def test_autofill_fills_the_demo_form_and_submits(live_server: str, browser_session, tmp_path, monkeypatch) -> None:
    from app.modules.browser.autofill import click_submit, fill_form

    monkeypatch.setattr(settings, "BROWSER_ACTION_DELAY_MS", 0)
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4 demo resume\n")
    answers = [
        _Answer("first_name", "Aarav"),
        _Answer("last_name", "Sharma"),
        _Answer("email", "aarav.sharma@example.com"),
        _Answer("phone", "+91 98765 43210"),
        _Answer("city", "Bangalore"),
        _Answer("linkedin_url", "https://linkedin.com/in/aarav"),
        _Answer("github_url", "https://github.com/aarav"),
        _Answer("resume_file", str(resume)),
        _Answer("years_of_experience", "2"),
        _Answer("skill_years:react", "2"),
        _Answer("current_salary", "800000"),
        _Answer("expected_salary", "1200000"),
        _Answer("notice_period_days", "30 days"),
        _Answer("work_authorization", "Yes"),
        _Answer("custom:why_us", "Your product solves a problem I have shipped against."),
        _Answer("custom:start_date", "1 November 2026"),
        _Answer("custom:consent", "true"),
        _Answer("portfolio_url", "", status="NEEDS_USER_INPUT"),
    ]

    browser_session.page.goto(f"{live_server}/demo-ats/jobs/{SLUG}/apply")
    detected = detect_form(browser_session.page)
    result = fill_form(browser_session.page, detected, answers, session=browser_session, application_id="test-app")

    filled = {f["key"] for f in result.filled}
    assert {"first_name", "resume_file", "notice_period_days", "work_authorization", "custom:consent"} <= filled
    assert len(result.filled) == 17
    # an explicit NEEDS_USER_INPUT answer is always surfaced, with `required` so the
    # runner can decide whether it must pause (portfolio is optional here)
    assert [(s["key"], s["required"]) for s in result.needs_user] == [("portfolio_url", False)]
    assert result.skipped == []
    assert result.screenshot_path and result.screenshot_path.endswith("after_fill.png")
    previews = {f["key"]: f["value_preview"] for f in result.filled}
    assert previews["email"] == "aa**********@example.com"
    assert previews["phone"].endswith("3210") and "98765" not in previews["phone"]
    assert previews["expected_salary"] == "1200000"

    html = click_submit(browser_session.page, detected)
    assert "Thank you for applying" in html
    assert re.search(r"Application ID: DEMO-[A-Z0-9]{6}", html)
