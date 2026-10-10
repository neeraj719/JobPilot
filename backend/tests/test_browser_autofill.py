"""Autofill rules (CONTRACTS.md section 12) against a fake page - no browser required.

The live-Chromium counterpart lives in ``test_browser_detector.py`` (``browser`` marker).
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.core.config import settings
from app.models.enums import FieldType
from app.modules.browser.autofill import click_submit, fill_form, mask_value
from app.modules.browser.schemas import DetectedField, DetectedForm, FieldOption


@dataclass
class Answer:
    question_key: str
    answer: str
    status: str = "ANSWERED"
    field_selector: str | None = None


class FakeLocator:
    def __init__(self, page: "FakePage", selector: str) -> None:
        self.page = page
        self.selector = selector

    @property
    def first(self) -> "FakeLocator":
        return self

    def fill(self, value: str) -> None:
        self.page.actions.append(("fill", self.selector, value))

    def check(self) -> None:
        self.page.actions.append(("check", self.selector, True))

    def uncheck(self) -> None:
        self.page.actions.append(("check", self.selector, False))

    def set_input_files(self, path: str) -> None:
        self.page.actions.append(("file", self.selector, path))

    def click(self) -> None:
        self.page.actions.append(("click", self.selector, None))

    def select_option(self, value: str | None = None, label: str | None = None) -> None:
        options = self.page.options.get(self.selector, [])
        if value is not None and any(v == value for v, _ in options):
            self.page.actions.append(("select", self.selector, value))
            return
        if label is not None and any(lab == label for _, lab in options):
            self.page.actions.append(("select", self.selector, label))
            return
        raise ValueError(f"no option {value or label!r} on {self.selector}")


class FakePage:
    def __init__(self, options: dict[str, list[tuple[str, str]]] | None = None) -> None:
        self.actions: list[tuple[str, str, object]] = []
        self.options = options or {}

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self, selector)

    def wait_for_load_state(self, state: str, timeout: int | None = None) -> None:
        self.actions.append(("wait", state, None))

    def content(self) -> str:
        return "<html><body>Thank you for applying. Application ID: DEMO-ABC123</body></html>"


@pytest.fixture(autouse=True)
def _no_delay(monkeypatch):
    monkeypatch.setattr(settings, "BROWSER_ACTION_DELAY_MS", 0)


def field(name: str, field_type: FieldType = FieldType.TEXT, *, label: str | None = None, required: bool = False, options=None):
    return DetectedField(
        selector=f"#{name}",
        name=name,
        id=name,
        label=label or name.replace("_", " ").title(),
        field_type=field_type,
        required=required,
        options=[FieldOption(value=v, label=lab, selector=f"#{name}_{v.lower()}") for v, lab in (options or [])],
    )


# --------------------------------------------------------------------------- matching


def test_fills_by_canonical_key() -> None:
    form = DetectedForm(fields=[field("first_name"), field("email", FieldType.EMAIL)])
    page = FakePage()
    result = fill_form(page, form, [Answer("first_name", "Aarav"), Answer("email", "a@example.com")])
    assert page.actions == [("fill", "#first_name", "Aarav"), ("fill", "#email", "a@example.com")]
    assert [f["key"] for f in result.filled] == ["first_name", "email"]
    assert result.ok


def test_field_selector_wins_over_the_canonical_key() -> None:
    form = DetectedForm(fields=[field("first_name")])
    page = FakePage()
    answers = [Answer("first_name", "FromKey"), Answer("custom:whatever", "FromSelector", field_selector="#first_name")]
    fill_form(page, form, answers)
    assert page.actions == [("fill", "#first_name", "FromSelector")]


def test_unanswered_required_field_needs_the_user() -> None:
    form = DetectedForm(fields=[field("email", FieldType.EMAIL, required=True), field("github", required=False)])
    result = fill_form(FakePage(), form, [])
    assert [s["key"] for s in result.needs_user] == ["email"]
    assert [s["key"] for s in result.skipped] == ["github_url"]
    assert result.ok is False


@pytest.mark.parametrize("status", ["NEEDS_USER_INPUT", "SKIPPED"])
def test_answers_that_are_not_answered_are_never_typed(status: str) -> None:
    form = DetectedForm(fields=[field("phone", FieldType.PHONE, required=True)])
    page = FakePage()
    result = fill_form(page, form, [Answer("phone", "+91 98765 43210", status=status)])
    assert page.actions == []
    assert [s["key"] for s in result.needs_user] == ["phone"]
    assert status in result.needs_user[0]["reason"]


def test_empty_answer_is_not_typed() -> None:
    form = DetectedForm(fields=[field("phone", FieldType.PHONE, required=True)])
    page = FakePage()
    result = fill_form(page, form, [Answer("phone", "   ")])
    assert page.actions == []
    assert result.needs_user[0]["reason"] == "answer is empty"


# --------------------------------------------------------------------------- widgets


def test_select_matches_an_option_fuzzily() -> None:
    notice = field(
        "notice_period",
        FieldType.SELECT,
        options=[("Immediate", "Immediate"), ("30 days", "30 days"), ("60 days", "60 days")],
    )
    page = FakePage(options={"#notice_period": [("Immediate", "Immediate"), ("30 days", "30 days"), ("60 days", "60 days")]})
    fill_form(page, DetectedForm(fields=[notice]), [Answer("notice_period_days", "30")])
    assert page.actions == [("select", "#notice_period", "30 days")]


def test_select_without_a_matching_option_asks_the_user() -> None:
    notice = field("notice_period", FieldType.SELECT, required=True, options=[("Immediate", "Immediate")])
    page = FakePage(options={"#notice_period": [("Immediate", "Immediate")]})
    result = fill_form(page, DetectedForm(fields=[notice]), [Answer("notice_period_days", "banana split")])
    assert page.actions == []
    assert "no select option matches" in result.needs_user[0]["reason"]


@pytest.mark.parametrize("answer,expected", [("Yes", "#work_authorization_yes"), ("true", "#work_authorization_yes"), ("No", "#work_authorization_no")])
def test_radio_uses_the_option_selector(answer: str, expected: str) -> None:
    radio = field(
        "work_authorization",
        FieldType.RADIO,
        label="Are you legally authorized to work in India?",
        options=[("Yes", "Yes"), ("No", "No")],
    )
    page = FakePage()
    fill_form(page, DetectedForm(fields=[radio]), [Answer("work_authorization", answer)])
    assert page.actions == [("check", expected, True)]


@pytest.mark.parametrize("answer,checked", [("true", True), ("yes", True), ("false", False), ("no", False)])
def test_checkbox_checks_and_unchecks(answer: str, checked: bool) -> None:
    consent = field("consent", FieldType.CHECKBOX, label="I consent to the terms")
    page = FakePage()
    fill_form(page, DetectedForm(fields=[consent]), [Answer("custom:consent", answer)])
    assert page.actions == [("check", "#consent", checked)]


def test_file_is_uploaded_when_it_exists(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    # attachments are only accepted from inside UPLOAD_DIR (see _resolve_upload_path)
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4")
    page = FakePage()
    form = DetectedForm(fields=[field("resume", FieldType.FILE, label="Resume/CV", required=True)])
    result = fill_form(page, form, [Answer("resume_file", str(resume))])
    assert page.actions == [("file", "#resume", str(resume))]
    assert result.filled[0]["value_preview"] == "resume.pdf"


def test_missing_file_asks_the_user(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    page = FakePage()
    form = DetectedForm(fields=[field("resume", FieldType.FILE, label="Resume/CV", required=True)])
    result = fill_form(page, form, [Answer("resume_file", str(tmp_path / "nope.pdf"))])
    assert page.actions == []
    assert "file not found" in result.needs_user[0]["reason"]


def test_a_failing_field_does_not_abort_the_rest() -> None:
    class Exploding(FakePage):
        def locator(self, selector: str):
            if selector == "#phone":
                raise RuntimeError("element detached")
            return super().locator(selector)

    form = DetectedForm(fields=[field("phone", FieldType.PHONE, required=True), field("email", FieldType.EMAIL)])
    page = Exploding()
    result = fill_form(page, form, [Answer("phone", "+91 90000 00000"), Answer("email", "a@example.com")])
    assert page.actions == [("fill", "#email", "a@example.com")]
    assert "fill failed" in result.needs_user[0]["reason"]


# --------------------------------------------------------------------------- previews / submit


@pytest.mark.parametrize(
    "value,field_type,expected",
    [
        ("aarav.sharma@example.com", FieldType.EMAIL, "aa**********@example.com"),
        ("+91 98765 43210", FieldType.PHONE, "********3210"),
        ("9876543210", FieldType.PHONE, "******3210"),
        ("1200000", FieldType.NUMBER, "1200000"),
        ("Bangalore", FieldType.TEXT, "Bangalore"),
        ("x" * 80, FieldType.TEXTAREA, "x" * 57 + "..."),
    ],
)
def test_value_previews_mask_contact_details(value: str, field_type: FieldType, expected: str) -> None:
    assert mask_value(value, field_type) == expected


def test_click_submit_waits_and_returns_the_page() -> None:
    page = FakePage()
    html = click_submit(page, DetectedForm(submit_selector='button[type="submit"]'))
    assert page.actions[0] == ("click", 'button[type="submit"]', None)
    assert [a[1] for a in page.actions[1:]] == ["load", "networkidle"]
    assert "Thank you for applying" in html


def test_click_submit_falls_back_to_a_generic_selector() -> None:
    page = FakePage()
    click_submit(page, DetectedForm())
    assert page.actions[0][1] == 'button[type="submit"], input[type="submit"]'
