"""Demo ATS adapter — the one adapter that drives a *real* browser.

The demo ATS is a Greenhouse-style career site served by this same backend at
``/demo-ats`` (see ``docs/CONTRACTS.md`` §12). It exists so the whole Playwright
autofill → review → submit flow can be demonstrated end to end without touching any
third-party website.

:class:`GenericAtsFormAdapter` holds the shared "hosted ATS form" flow
(navigate → detect → map → fill → submit) which Greenhouse/Lever reuse. Every
Playwright and browser-module import is **lazy** so importing this module never
requires a browser to be installed.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from app.core.config import settings
from app.models.enums import (
    ApplicationType,
    AutomationState,
    EmploymentType,
    JobSourceType,
    PauseReason,
    WorkMode,
)
from app.modules.adapters.base import (
    ApplyContext,
    ApplyStepResult,
    AuthResult,
    DiscoveredJob,
    JobSourceAdapter,
    SearchQuery,
)

logger = logging.getLogger(__name__)

APPLICATION_ID_RE = re.compile(r"Application ID:\s*(DEMO-[A-Z0-9]+)", re.IGNORECASE)
CONFIRMATION_TEXT = "Thank you for applying"
#: The browser only ever navigates to the web - never file://, data: or javascript:.
ALLOWED_APPLY_SCHEMES = frozenset({"http", "https"})
HTTP_TIMEOUT_SECONDS = 5.0


# --------------------------------------------------------------------------- generic ATS


class GenericAtsFormAdapter(JobSourceAdapter):
    """Shared flow for hosted ATS application forms (Greenhouse, Lever, demo ATS).

    The three steps mirror :class:`~app.modules.adapters.base.JobSourceAdapter`:

    ``start_application``   navigate the page to ``job.apply_url`` and wait for a form
    ``fill_application``    ``detect_form`` → blockers? → map fields → merge answers → ``fill_form``
    ``submit_application``  click submit, wait for the confirmation, capture the reference
    """

    is_mock = False
    supports_auto_apply = True
    requires_account = False
    uses_browser = True
    rate_limit_per_minute = 20
    submit_selectors: tuple[str, ...] = (
        "button[type=submit]",
        "input[type=submit]",
        "#submit_app",
        "button:has-text('Submit')",
    )
    confirmation_text: str = CONFIRMATION_TEXT
    application_id_pattern: re.Pattern[str] = APPLICATION_ID_RE

    # -- discovery ---------------------------------------------------------

    def search_jobs(self, query: SearchQuery) -> list[DiscoveredJob]:  # pragma: no cover - overridden
        return []

    def authenticate(self, session: Any | None = None, credentials: dict[str, Any] | None = None) -> AuthResult:
        """Hosted ATS forms are public — no account and no credentials are used."""
        return AuthResult(ok=True, message=f"{self.display_name} needs no account", is_mock=False)

    def detect_application_type(self, job: DiscoveredJob) -> ApplicationType:
        return ApplicationType.ATS_FORM

    # -- step 1: navigate --------------------------------------------------

    def start_application(self, ctx: ApplyContext) -> ApplyStepResult:
        page = ctx.page
        if page is None:
            return ApplyStepResult(state=AutomationState.FAILED, message="browser page required")
        apply_url = getattr(ctx.job, "apply_url", None) or getattr(ctx.job, "canonical_url", None)
        if not apply_url:
            return ApplyStepResult(state=AutomationState.FAILED, message="Job has no apply URL")
        # The apply URL comes from a job source. Only ever drive the browser to the web:
        # file://, data: and javascript: would turn a bad listing into local-file access
        # or script execution inside the automation context.
        if urlparse(str(apply_url)).scheme.lower() not in ALLOWED_APPLY_SCHEMES:
            logger.warning("%s refused a non-http(s) apply URL: %s", self.display_name, apply_url)
            return ApplyStepResult(
                state=AutomationState.FAILED,
                message="The application URL is not an http(s) address; JobPilot will not open it.",
            )
        try:
            page.goto(apply_url, timeout=settings.BROWSER_TIMEOUT_MS, wait_until="domcontentloaded")
            page.wait_for_selector("form", timeout=settings.BROWSER_TIMEOUT_MS)
        except Exception as exc:  # pragma: no cover - needs a live browser
            logger.warning("%s could not open %s: %s", self.display_name, apply_url, exc)
            return ApplyStepResult(state=AutomationState.FAILED, message=f"Could not open the application form: {exc}")
        return ApplyStepResult(
            state=AutomationState.SUCCESS,
            message=f"Opened {self.display_name} application form",
            form_snapshot={"url": apply_url},
        )

    # -- step 2: detect + map + fill ---------------------------------------

    def fill_application(self, ctx: ApplyContext) -> ApplyStepResult:
        page = ctx.page
        if page is None:
            return ApplyStepResult(state=AutomationState.FAILED, message="browser page required")
        try:
            from app.modules.browser.autofill import fill_form
            from app.modules.browser.detector import detect_form
        except ImportError as exc:  # browser module not available yet
            logger.warning("Browser module unavailable: %s", exc)
            return ApplyStepResult(state=AutomationState.FAILED, message="Browser automation module is not available")

        try:
            detected = detect_form(page)
        except Exception as exc:  # pragma: no cover - needs a live browser
            return ApplyStepResult(state=AutomationState.FAILED, message=f"Could not read the application form: {exc}")

        blockers = list(getattr(detected, "blockers", None) or [])
        if blockers:
            first = blockers[0]
            reason = getattr(first, "kind", None) or PauseReason.OTHER
            message = getattr(first, "message", None) or f"{self.display_name} needs you to continue manually"
            logger.info("%s paused on a blocker: %s", self.display_name, reason)
            return ApplyStepResult(
                state=AutomationState.REQUIRES_USER,
                message=message,
                pause_reason=reason if isinstance(reason, PauseReason) else PauseReason.OTHER,
                form_snapshot=self._snapshot(detected, [], blockers),
            )

        answers = list(ctx.answers or [])
        mapped = self._map_fields(detected)
        answers_by_key = {str(getattr(a, "question_key", "")): a for a in answers}
        unanswered_required: list[str] = []
        for field, canonical_key in mapped:
            if not getattr(field, "required", False):
                continue
            answer = answers_by_key.get(canonical_key or "")
            value = getattr(answer, "answer", None) if answer is not None else None
            if value in (None, ""):
                unanswered_required.append(getattr(field, "label", None) or canonical_key or "unnamed field")

        if unanswered_required:
            logger.info("%s is missing %d required answers", self.display_name, len(unanswered_required))

        # Fill everything the profile *does* know before pausing (contract §12: detect -> map ->
        # merge -> fill -> pause). Stopping earlier would hand the reviewer an empty form snapshot
        # and no screenshot, and the gaps are reported all the same via ``missing``/``needs_user``.
        application_id = getattr(ctx.application, "id", None)
        try:
            try:
                result = fill_form(page, detected, answers, application_id=application_id)
            except TypeError:  # older/leaner signature
                result = fill_form(page, detected, answers)
        except Exception as exc:  # pragma: no cover - needs a live browser
            return ApplyStepResult(state=AutomationState.FAILED, message=f"Could not fill the application form: {exc}")

        snapshot = self._snapshot(detected, mapped, blockers, missing=unanswered_required)
        snapshot["filled"] = list(getattr(result, "filled", None) or [])
        snapshot["skipped"] = list(getattr(result, "skipped", None) or [])
        needs_user = list(getattr(result, "needs_user", None) or [])
        snapshot["needs_user"] = needs_user
        screenshot_path = getattr(result, "screenshot_path", None)
        if unanswered_required or needs_user:
            if unanswered_required:
                message = "Some required questions could not be answered from your profile: " + ", ".join(
                    unanswered_required
                )
            else:
                message = "Some fields still need your input"
            return ApplyStepResult(
                state=AutomationState.REQUIRES_USER,
                message=message,
                pause_reason=PauseReason.UNKNOWN_QUESTION,
                form_snapshot=snapshot,
                screenshot_path=screenshot_path,
            )
        return ApplyStepResult(
            state=AutomationState.SUCCESS,
            message=f"Filled {len(snapshot['filled'])} fields on the {self.display_name} form",
            form_snapshot=snapshot,
            screenshot_path=screenshot_path,
        )

    # -- step 3: submit ----------------------------------------------------

    def submit_application(self, ctx: ApplyContext) -> ApplyStepResult:
        page = ctx.page
        if page is None:
            return ApplyStepResult(state=AutomationState.FAILED, message="browser page required")
        selector = self._submit_selector(ctx)
        try:
            page.click(selector, timeout=settings.BROWSER_TIMEOUT_MS)
            page.wait_for_load_state("domcontentloaded", timeout=settings.BROWSER_TIMEOUT_MS)
            try:
                page.wait_for_selector(f"text={self.confirmation_text}", timeout=settings.BROWSER_TIMEOUT_MS)
            except Exception:  # confirmation wording may differ; fall back to the page text
                logger.info("%s: confirmation text not found, reading page content", self.display_name)
            content = page.content()
        except Exception as exc:  # pragma: no cover - needs a live browser
            logger.warning("%s submit failed: %s", self.display_name, exc)
            return ApplyStepResult(state=AutomationState.FAILED, message=f"Could not submit the application: {exc}")

        match = self.application_id_pattern.search(content or "")
        external_id = match.group(1) if match else None
        confirmed = self.confirmation_text.lower() in (content or "").lower()
        if not confirmed and external_id is None:
            return ApplyStepResult(
                state=AutomationState.FAILED,
                message="Submitted the form but no confirmation was found on the page",
            )
        return ApplyStepResult(
            state=AutomationState.SUCCESS,
            message=f"Submitted the {self.display_name} application",
            external_application_id=external_id,
            confirmation_message=f"{self.confirmation_text}. Reference {external_id}." if external_id else self.confirmation_text,
        )

    # -- helpers -----------------------------------------------------------

    def _submit_selector(self, ctx: ApplyContext) -> str:
        snapshot = getattr(ctx.application, "form_snapshot", None) or {}
        selector = snapshot.get("submit_selector") if isinstance(snapshot, dict) else None
        return selector or self.submit_selectors[0]

    @staticmethod
    def _map_fields(detected: Any) -> list[tuple[Any, str | None]]:
        """Map every detected field to a canonical key using the browser field mapper."""
        try:
            from app.modules.browser.mapper import FieldMapper
        except ImportError:  # pragma: no cover - browser module not written yet
            return [(f, None) for f in (getattr(detected, "fields", None) or [])]
        mapper = FieldMapper()
        out: list[tuple[Any, str | None]] = []
        for field in getattr(detected, "fields", None) or []:
            try:
                mapping = mapper.map(field)
            except Exception:  # pragma: no cover - defensive
                out.append((field, None))
                continue
            out.append((field, getattr(mapping, "canonical_key", None)))
        return out

    @staticmethod
    def _snapshot(
        detected: Any,
        mapped: list[tuple[Any, str | None]],
        blockers: list[Any],
        *,
        missing: list[str] | None = None,
    ) -> dict[str, Any]:
        fields = []
        for field, key in mapped:
            fields.append(
                {
                    "key": key,
                    "label": getattr(field, "label", None),
                    "selector": getattr(field, "selector", None),
                    "field_type": str(getattr(field, "field_type", "") or ""),
                    "mapped_to": key,
                    "required": bool(getattr(field, "required", False)),
                }
            )
        return {
            "url": getattr(detected, "url", None),
            "submit_selector": getattr(detected, "submit_selector", None),
            "fields": fields,
            "blockers": [
                {
                    "kind": str(getattr(b, "kind", "") or ""),
                    "selector": getattr(b, "selector", None),
                    "message": getattr(b, "message", None),
                }
                for b in blockers
            ],
            "missing": missing or [],
        }


# --------------------------------------------------------------------------- demo ATS


class DemoAtsAdapter(GenericAtsFormAdapter):
    """The local Greenhouse-style demo career site bundled with this backend.

    ``search_jobs`` reads ``DEMO_ATS_BASE_URL/demo-ats/jobs.json``; if the endpoint is
    unreachable it falls back to importing the catalogue module directly, so discovery
    also works in tests and offline.
    """

    source = JobSourceType.DEMO_ATS
    display_name = "Demo ATS"
    is_mock = False
    supports_auto_apply = True
    requires_account = False
    uses_browser = True
    rate_limit_per_minute = 60
    terms_note = (
        "This career site is part of JobPilot itself and exists so the Playwright flow can be "
        "demonstrated safely. It is the only site the automation submits to out of the box, and it "
        "renders an optional fake CAPTCHA so the pause-for-human behaviour can be shown (never solved)."
    )

    # -- urls --------------------------------------------------------------

    @property
    def base_url(self) -> str:
        return settings.DEMO_ATS_BASE_URL.rstrip("/")

    def jobs_json_url(self) -> str:
        return f"{self.base_url}/demo-ats/jobs.json"

    def job_url(self, slug: str) -> str:
        return f"{self.base_url}/demo-ats/jobs/{slug}"

    def apply_url(self, slug: str) -> str:
        return f"{self.base_url}/demo-ats/jobs/{slug}/apply"

    # -- discovery ---------------------------------------------------------

    def _fetch_payload(self) -> list[dict[str, Any]]:
        try:
            import httpx

            response = httpx.get(self.jobs_json_url(), timeout=HTTP_TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.info("Demo ATS endpoint unavailable (%s); falling back to the local catalogue", exc)
            return self._fallback_payload()
        if isinstance(payload, dict):
            payload = payload.get("jobs") or payload.get("items") or []
        if not isinstance(payload, list):
            logger.warning("Demo ATS returned an unexpected payload type: %s", type(payload).__name__)
            return self._fallback_payload()
        return [row for row in payload if isinstance(row, dict)]

    @staticmethod
    def _fallback_payload() -> list[dict[str, Any]]:
        try:
            from app.demo_ats.catalog import DEMO_JOBS  # type: ignore[attr-defined]
        except Exception as exc:
            logger.info("Demo ATS local catalogue unavailable (%s); returning no jobs", exc)
            return []
        return [row for row in list(DEMO_JOBS or []) if isinstance(row, dict)]

    def catalogue(self, now: datetime | None = None) -> list[DiscoveredJob]:
        now = now or datetime.now(timezone.utc)
        return [self._to_discovered_job(row, now) for row in self._fetch_payload() if row.get("slug")]

    def search_jobs(self, query: SearchQuery) -> list[DiscoveredJob]:
        from app.modules.adapters.mock.base_mock import filter_catalogue

        now = datetime.now(timezone.utc)
        jobs = self.catalogue(now)
        results = filter_catalogue(jobs, query, now)
        logger.info("Demo ATS search returned %d/%d jobs", len(results), len(jobs))
        return results

    def get_job_details(self, external_id: str) -> DiscoveredJob | None:
        for job in self.catalogue():
            if job.external_id == external_id:
                return job
        return None

    def _to_discovered_job(self, row: dict[str, Any], now: datetime) -> DiscoveredJob:
        slug = str(row.get("slug"))
        posted_hours = row.get("posted_hours_ago")
        try:
            posted_at = now - timedelta(hours=float(posted_hours)) if posted_hours is not None else now
        except (TypeError, ValueError):
            posted_at = now
        return DiscoveredJob(
            source=self.source,
            external_id=slug,
            url=self.job_url(slug),
            title=str(row.get("title") or "Software Engineer"),
            company_name=str(row.get("company") or "Demo Company"),
            location=row.get("location"),
            work_mode=_enum_or_none(WorkMode, row.get("work_mode")),
            employment_type=_enum_or_none(EmploymentType, row.get("employment_type")),
            description=str(row.get("description") or ""),
            required_skills=list(row.get("required_skills") or []),
            preferred_skills=list(row.get("preferred_skills") or []),
            experience_min=_float_or_none(row.get("experience_min")),
            experience_max=_float_or_none(row.get("experience_max")),
            salary_min=_int_or_none(row.get("salary_min")),
            salary_max=_int_or_none(row.get("salary_max")),
            salary_currency=row.get("salary_currency") or "INR",
            posted_at=posted_at,
            apply_url=self.apply_url(slug),
            application_type=ApplicationType.ATS_FORM,
            company_domain=row.get("company_domain"),
            company_logo_url=row.get("logo_url"),
            raw={"demo_ats": True, "slug": slug},
        )


# --------------------------------------------------------------------------- coercion helpers


def _enum_or_none(enum_cls: Any, value: Any) -> Any:
    if value is None or value == "":
        return None
    try:
        return enum_cls(value)
    except ValueError:
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None
