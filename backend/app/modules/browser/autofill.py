"""Fill a detected form with pre-generated answers (CONTRACTS.md section 12).

``fill_form`` is deliberately conservative: it only types values that a human already
approved or that came from the profile/resume, it never guesses, and anything it cannot
place is reported in ``needs_user`` so the runner can pause instead of submitting
half-complete applications.
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

from app.core.config import settings
from app.models.enums import FieldType
from app.modules.browser.mapper import default_mapper
from app.modules.browser.schemas import DetectedField, DetectedForm, FilledField, FillResult, SkippedField

logger = logging.getLogger(__name__)

TRUE_WORDS = {"true", "yes", "y", "1", "on", "agree", "agreed", "checked", "accept", "accepted"}
FALSE_WORDS = {"false", "no", "n", "0", "off", "decline", "declined", "unchecked"}
_EMAIL_RE = re.compile(r"^([^@\s]+)@([^@\s]+)$")
_ANSWERED = "ANSWERED"
_NEEDS_USER = "NEEDS_USER_INPUT"


# --------------------------------------------------------------------------- helpers


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _answer_text(answer: Any) -> str:
    return str(getattr(answer, "answer", "") or "").strip()


def mask_value(value: str, field_type: FieldType = FieldType.TEXT) -> str:
    """Short, log-safe preview of what was typed (emails/phones partially masked)."""
    value = (value or "").strip()
    if not value:
        return ""
    email = _EMAIL_RE.match(value)
    if email:
        local, domain = email.groups()
        head = local[:2] if len(local) > 2 else local[:1]
        return f"{head}{'*' * max(3, len(local) - len(head))}@{domain}"
    digits = re.sub(r"\D", "", value)
    phone_shaped = bool(re.search(r"[\s+()-]", value)) and len(re.sub(r"[\d\s+()-]", "", value)) == 0
    if 7 <= len(digits) <= 15 and (field_type is FieldType.PHONE or phone_shaped):
        return f"{'*' * (len(digits) - 4)}{digits[-4:]}"
    if field_type is FieldType.FILE:
        return Path(value).name
    return value if len(value) <= 60 else value[:57] + "..."


def _truthy(value: str) -> bool:
    return value.strip().lower() in TRUE_WORDS


def _falsy(value: str) -> bool:
    return value.strip().lower() in FALSE_WORDS


def _best_option(value: str, options: Iterable[Any], *, cutoff: int = 55) -> Any | None:
    """Fuzzy-match an answer against the labels/values of a select or radio group."""
    options = list(options)
    if not options:
        return None
    needle = value.strip().lower()
    if not needle:
        return None
    for option in options:  # exact first
        if needle in (option.label.strip().lower(), option.value.strip().lower()):
            return option
    if _truthy(needle) or _falsy(needle):
        target = "yes" if _truthy(needle) else "no"
        for option in options:
            if option.label.strip().lower().startswith(target) or option.value.strip().lower().startswith(target):
                return option
    try:
        from rapidfuzz import fuzz

        scored = [
            (max(fuzz.token_set_ratio(needle, option.label.lower()), fuzz.token_set_ratio(needle, option.value.lower())), option)
            for option in options
        ]
        score, option = max(scored, key=lambda item: item[0])
        if score >= cutoff:
            return option
    except Exception as exc:  # pragma: no cover - rapidfuzz always present in requirements
        logger.debug("Fuzzy option match unavailable: %s", exc)
    for option in options:  # substring fallback
        if needle in option.label.lower() or option.label.lower() in needle:
            return option
    return None


def _pick_answer(field: DetectedField, by_selector: dict[str, Any], by_key: dict[str, Any]) -> tuple[Any | None, str | None]:
    """Selector match first (exact DOM identity), then the canonical key."""
    answer = by_selector.get(field.selector)
    if answer is not None:
        return answer, str(getattr(answer, "question_key", "") or "") or None
    key = default_mapper.map(field).canonical_key
    if key and key in by_key:
        return by_key[key], key
    return None, key


# --------------------------------------------------------------------------- filling


def fill_form(
    page: Any,
    detected: DetectedForm,
    answers: Sequence[Any],
    *,
    session: Any | None = None,
    application_id: Any | None = None,
    screenshot_name: str = "after_fill",
) -> FillResult:
    """Type every answered value into the live form.

    ``answers`` items are duck-typed: anything exposing ``question_key``, ``answer``,
    ``status`` and ``field_selector`` works (``ApplicationAnswer`` rows or dataclasses).
    Answers that are not ``ANSWERED``, are empty, or point at a missing file are
    reported in ``needs_user`` / ``skipped`` - never invented.

    Pass ``session`` (a ``BrowserSessionHandle``) plus ``application_id`` to capture the
    post-fill screenshot into ``UPLOAD_DIR/screenshots/<application_id>/``.
    """
    by_selector: dict[str, Any] = {}
    by_key: dict[str, Any] = {}
    for answer in answers or []:
        selector = getattr(answer, "field_selector", None)
        if selector and selector not in by_selector:
            by_selector[selector] = answer
        key = str(getattr(answer, "question_key", "") or "")
        if key and key not in by_key:
            by_key[key] = answer

    result = FillResult()
    delay = max(0.0, settings.BROWSER_ACTION_DELAY_MS / 1000)
    first = True

    for field in detected.fields:
        answer, key = _pick_answer(field, by_selector, by_key)

        def _report(reason: str, *, needs_user: bool) -> None:
            row: SkippedField = {
                "selector": field.selector,
                "key": key,
                "label": field.label,
                "required": field.required,
                "reason": reason,
            }
            (result.needs_user if needs_user else result.skipped).append(row)

        if answer is None:
            _report("no answer available for this field", needs_user=field.required)
            continue
        status = _enum_value(getattr(answer, "status", None))
        if status and status != _ANSWERED:
            _report(f"answer status is {status}", needs_user=status == _NEEDS_USER or field.required)
            continue
        value = _answer_text(answer)
        if not value:
            _report("answer is empty", needs_user=field.required)
            continue

        if not first and delay:
            time.sleep(delay)
        first = False
        try:
            outcome = _fill_field(page, field, value)
        except Exception as exc:
            logger.warning("Could not fill %s (%s): %s", field.selector, field.label, exc)
            _report(f"fill failed: {exc.__class__.__name__}: {exc}", needs_user=field.required)
            continue
        if outcome is None:
            row: FilledField = {
                "selector": field.selector,
                "key": key,
                "value_preview": mask_value(value, field.field_type),
                "field_type": field.field_type.value,
            }
            result.filled.append(row)
        else:
            _report(outcome, needs_user=field.required)

    if session is not None or application_id is not None:
        try:
            from app.modules.browser.session import save_screenshot

            result.screenshot_path = (
                session.screenshot(screenshot_name, application_id)
                if session is not None
                else save_screenshot(page, screenshot_name, application_id)
            ) or None
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Post-fill screenshot failed: %s", exc)

    logger.info(
        "Form fill finished: %d filled, %d skipped, %d need the user",
        len(result.filled),
        len(result.skipped),
        len(result.needs_user),
    )
    return result


def _resolve_upload_path(value: str) -> tuple[Path | None, str | None]:
    """Validate the path of a file answer before handing it to the browser.

    Anything a form asks us to attach must be a file JobPilot itself stored under
    ``UPLOAD_DIR``. Without this rail, a path that reached an answer row (a crafted
    answer, a corrupted profile fact) would be uploaded verbatim to a third-party
    site -- an arbitrary server-file read with built-in exfiltration.
    """
    raw = (value or "").strip()
    if not raw:
        return None, "no file to attach"
    try:
        path = Path(raw).expanduser().resolve()
        root = Path(settings.UPLOAD_DIR).expanduser().resolve()
    except OSError as exc:  # pragma: no cover - defensive
        return None, f"invalid file path: {exc}"
    if path != root and root not in path.parents:
        logger.warning("Refusing to attach %s: outside the upload directory", path)
        return None, "file is outside the allowed upload directory"
    if not path.is_file():
        return None, f"file not found: {raw}"
    return path, None


def _fill_field(page: Any, field: DetectedField, value: str) -> str | None:
    """Type one value. Returns ``None`` on success or a human reason why it could not."""
    locator = page.locator(field.selector).first

    if field.field_type is FieldType.FILE:
        path, reason = _resolve_upload_path(value)
        if path is None:
            return reason
        locator.set_input_files(str(path))
        return None

    if field.field_type is FieldType.CHECKBOX:
        if _falsy(value):
            locator.uncheck()
        else:
            locator.check()
        return None

    if field.field_type is FieldType.RADIO:
        option = _best_option(value, field.options)
        if option is None:
            return f"no radio option matches {value!r} (options: {[o.label for o in field.options]})"
        selector = option.selector or (
            f'input[type="radio"][name="{field.name}"][value="{option.value}"]' if field.name else field.selector
        )
        page.locator(selector).first.check()
        return None

    if field.field_type is FieldType.SELECT:
        option = _best_option(value, field.options)
        if option is not None:
            try:
                locator.select_option(value=option.value)
                return None
            except Exception:
                locator.select_option(label=option.label)
                return None
        try:
            locator.select_option(label=value)
            return None
        except Exception:
            try:
                locator.select_option(value=value)
                return None
            except Exception:
                return f"no select option matches {value!r} (options: {[o.label for o in field.options]})"

    # text / textarea / email / tel / number / url / date
    locator.fill(value)
    return None


# --------------------------------------------------------------------------- submit


def click_submit(page: Any, detected: DetectedForm) -> str:
    """Click the submit control and return the resulting page HTML.

    Only ever called from the human-approved path (``applications.service.approve``) or
    an explicitly enabled auto-submit source.
    """
    selector = detected.submit_selector or 'button[type="submit"], input[type="submit"]'
    logger.info("Submitting form via %s", selector)
    page.locator(selector).first.click()
    for state in ("load", "networkidle"):
        try:
            page.wait_for_load_state(state, timeout=settings.BROWSER_TIMEOUT_MS)
        except Exception as exc:  # pragma: no cover - network dependent
            logger.debug("wait_for_load_state(%s) timed out: %s", state, exc)
    return page.content()
