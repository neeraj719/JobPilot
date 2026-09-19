"""End-to-end smoke test for a *running* JobPilot AI backend.

Drives the public HTTP API exactly the way the frontend does — log in as the demo user,
read every list screen, discover jobs, run the automation pipeline, and let a simulated
ATS email move an application forward. Nothing is mocked: point it at any deployment
(local uvicorn, docker-compose, staging) and it reports PASS/FAIL per step.

Usage::

    # terminal 1
    cd backend
    DATABASE_URL=sqlite+pysqlite:///./smoke.db ENV=development \
        ./.venv/Scripts/python.exe -m alembic upgrade head
    DATABASE_URL=sqlite+pysqlite:///./smoke.db ./.venv/Scripts/python.exe -m app.seed
    DATABASE_URL=sqlite+pysqlite:///./smoke.db DEMO_ATS_BASE_URL=http://localhost:8010 \
        ./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8010

    # terminal 2
    ./.venv/Scripts/python.exe scripts/smoke_e2e.py --base-url http://localhost:8010
    ./.venv/Scripts/python.exe scripts/smoke_e2e.py --with-browser   # + the Playwright path

Exit code is 0 only when every step passed.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx

# Allow "python scripts/smoke_e2e.py" from anywhere in the repo.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_EMAIL = "demo@jobpilot.ai"
DEFAULT_PASSWORD = "DemoPass123!"

#: Read-only list screens every deployment must be able to serve.
READ_ONLY_ENDPOINTS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("/profile", {}),
    ("/resumes", {}),
    ("/jobs", {"page_size": 5}),
    ("/jobs/sources", {}),
    ("/companies/preferences", {}),
    ("/applications/queue", {}),
    ("/applications", {"page_size": 5}),
    ("/dashboard/stats", {}),
    ("/dashboard/charts", {}),
    ("/automation/config", {}),
    ("/automation/status", {}),
    ("/emails", {}),
    ("/integrations", {}),
    ("/notifications", {}),
    ("/audit", {}),
    ("/interviews", {}),
    ("/ai/status", {}),
    ("/browser/status", {}),
)


def _default_credentials() -> tuple[str, str]:
    """Demo credentials from the backend settings when importable, else the documented ones."""
    try:
        from app.core.config import settings

        return settings.DEMO_USER_EMAIL, settings.DEMO_USER_PASSWORD
    except Exception:  # noqa: BLE001 - the script must also run without the app package
        return DEFAULT_EMAIL, DEFAULT_PASSWORD


# --------------------------------------------------------------------------- reporting


class StepFailed(AssertionError):
    """A smoke step that did not meet its expectation."""


@dataclass
class Report:
    steps: list[str] = field(default_factory=list)
    failures: int = 0

    def record(self, name: str, ok: bool, detail: str = "", seconds: float = 0.0) -> None:
        status = "PASS" if ok else "FAIL"
        line = f"{status} {name}"
        if detail:
            line = f"{line} - {detail}"
        self.steps.append(line)
        if not ok:
            self.failures += 1
        print(f"[{status}] {name}{f' ({seconds:.2f}s)' if seconds else ''}{f' - {detail}' if detail else ''}", flush=True)


class Smoke:
    """Thin HTTP helper: every call asserts a 2xx and keeps the bearer token."""

    def __init__(self, base_url: str, report: Report, *, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api = f"{self.base_url}/api/v1"
        self.report = report
        self.client = httpx.Client(timeout=timeout, follow_redirects=True)

    def close(self) -> None:
        self.client.close()

    # -- plumbing ---------------------------------------------------------

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        response = self.client.request(method, url, **kwargs)
        if response.status_code >= 300:
            raise StepFailed(f"{method} {url} -> {response.status_code}: {response.text[:400]}")
        return response

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", f"{self.api}{path}", **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", f"{self.api}{path}", **kwargs)

    def put(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", f"{self.api}{path}", **kwargs)

    def step(self, name: str, fn: Callable[[], Any]) -> Any:
        started = time.monotonic()
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 - one failing step must not stop the rest
            self.report.record(name, False, f"{type(exc).__name__}: {exc}", time.monotonic() - started)
            return None
        detail = result if isinstance(result, str) else ""
        self.report.record(name, True, detail, time.monotonic() - started)
        return result if not isinstance(result, str) else result


# --------------------------------------------------------------------------- steps


def login(smoke: Smoke, email: str, password: str) -> str:
    body = smoke.post("/auth/login", json={"email": email, "password": password}).json()
    token = body["access_token"]
    smoke.client.headers.update({"Authorization": f"Bearer {token}"})
    return f"{email} authenticated"


def read_only_screens(smoke: Smoke) -> None:
    for path, params in READ_ONLY_ENDPOINTS:
        def _call(path: str = path, params: dict[str, Any] = params) -> str:
            payload = smoke.get(path, params=params).json()
            if isinstance(payload, dict) and "items" in payload:
                return f"{payload.get('total', len(payload['items']))} item(s)"
            return "ok"

        smoke.step(f"GET {path}", _call)


def demo_ats_pages(smoke: Smoke) -> None:
    def _index() -> str:
        html = smoke.request("GET", f"{smoke.base_url}/demo-ats/").text
        if "<html" not in html.lower():
            raise StepFailed("the demo ATS index did not return HTML")
        return f"{len(html)} bytes of HTML"

    def _jobs() -> str:
        postings = smoke.request("GET", f"{smoke.base_url}/demo-ats/jobs.json").json()
        if not isinstance(postings, list) or not postings:
            raise StepFailed(f"expected a non-empty list of postings, got {type(postings).__name__}")
        return f"{len(postings)} demo postings"

    smoke.step("GET /demo-ats/", _index)
    smoke.step("GET /demo-ats/jobs.json", _jobs)


def discover_jobs(smoke: Smoke) -> None:
    def _discover() -> str:
        body = smoke.post("/jobs/discover", json={"limit": 20}).json()
        if int(body.get("jobs_found", 0)) <= 0:
            raise StepFailed(f"discovery found no jobs: {json.dumps(body)[:300]}")
        return f"{body['jobs_found']} found, {body.get('jobs_new', 0)} new, {body.get('duplicates_merged', 0)} merged"

    smoke.step("POST /jobs/discover", _discover)


def automation_run(smoke: Smoke, poll_seconds: float) -> None:
    def _run() -> str:
        run = smoke.post("/automation/run", json={"dry_run": False}).json()
        run_id = run["id"]
        deadline = time.monotonic() + poll_seconds
        while time.monotonic() < deadline:
            run = smoke.get(f"/automation/runs/{run_id}").json()
            if run["status"] not in ("RUNNING", "PENDING"):
                break
            time.sleep(1.0)
        else:
            raise StepFailed(f"run {run_id} was still {run['status']} after {poll_seconds:.0f}s")

        if run["status"] not in ("SUCCESS", "PARTIAL"):
            raise StepFailed(f"run finished {run['status']}: {run.get('error')}")
        stats = run.get("stats") or {}
        if int(stats.get("jobs_found", 0)) <= 0:
            raise StepFailed(f"run reported no jobs_found: {json.dumps(stats)[:300]}")
        return f"{run['status']}, jobs_found={stats['jobs_found']}, queued={stats.get('queued', 0)}"

    smoke.step("POST /automation/run + poll to completion", _run)


def _first_application(smoke: Smoke, status: str) -> dict[str, Any] | None:
    body = smoke.get("/applications", params={"status": status, "page_size": 1}).json()
    items = body.get("items") or []
    return items[0] if items else None


def simulate_email(smoke: Smoke) -> None:
    def _simulate() -> str:
        application = _first_application(smoke, "APPLIED")
        if application is None:
            raise StepFailed("no APPLIED application to simulate a reply for")
        before = smoke.get("/dashboard/stats").json()["today"]["responses"]

        email = smoke.post(
            "/emails/simulate",
            json={"application_id": application["id"], "kind": "APPLICATION_RECEIVED"},
        ).json()
        if email.get("classification") != "APPLICATION_RECEIVED":
            raise StepFailed(f"email was classified {email.get('classification')}")

        detail = smoke.get(f"/applications/{application['id']}").json()
        if detail["status"] != "APPLICATION_RECEIVED":
            raise StepFailed(f"application status is {detail['status']}, expected APPLICATION_RECEIVED")

        after = smoke.get("/dashboard/stats").json()["today"]["responses"]
        if after <= before:
            raise StepFailed(f"dashboard today.responses did not increase ({before} -> {after})")
        return f"{application['id'][:8]} -> APPLICATION_RECEIVED, today.responses {before} -> {after}"

    smoke.step("POST /emails/simulate moves an application forward", _simulate)


# --------------------------------------------------------------------------- browser path


def _pick_demo_ats_job(smoke: Smoke) -> dict[str, Any]:
    body = smoke.get("/jobs", params={"source": "DEMO_ATS", "page_size": 50, "status": "NONE"}).json()
    items = body.get("items") or []
    if not items:
        raise StepFailed("no un-applied DEMO_ATS job to drive the browser with")
    return items[0]


def browser_path(smoke: Smoke, poll_seconds: float) -> None:
    """Queue a demo-ATS job and take it through autofill -> review -> approve -> email."""
    state: dict[str, Any] = {}

    def _queue() -> str:
        job = _pick_demo_ats_job(smoke)
        queued = smoke.post(f"/jobs/{job['id']}/queue").json()
        state["application_id"] = queued["id"]
        state["job"] = job
        return f"{job['title']} @ {job['company']['name']}"

    def _start() -> str:
        application_id = state["application_id"]
        smoke.post(f"/applications/{application_id}/start", json={"run_in_background": True})
        deadline = time.monotonic() + poll_seconds
        detail: dict[str, Any] = {}
        while time.monotonic() < deadline:
            detail = smoke.get(f"/applications/{application_id}").json()
            if detail["automation_state"] in ("PAUSED", "REQUIRES_USER", "FAILED"):
                break
            time.sleep(1.0)
        else:
            raise StepFailed(f"autofill was still {detail.get('automation_state')} after {poll_seconds:.0f}s")
        if detail["automation_state"] == "FAILED":
            raise StepFailed(f"autofill failed: {detail.get('last_error')}")
        state["detail"] = detail
        return f"{detail['automation_state']} ({detail.get('pause_reason')})"

    def _snapshot() -> str:
        snapshot = state["detail"].get("form_snapshot") or {}
        fields = snapshot.get("fields") or []
        filled = snapshot.get("filled") or []
        detected_keys = {str(row.get("key")) for row in fields}
        filled_keys = {str(row.get("key")) for row in filled}
        expected = {
            "first_name",
            "last_name",
            "email",
            "phone",
            "linkedin_url",
            "github_url",
            "resume_file",
            "years_of_experience",
            "expected_salary",
        }
        undetected = sorted(expected - detected_keys)
        if undetected:
            raise StepFailed(f"the detector missed {undetected} (found {sorted(detected_keys)})")
        unfilled = sorted(expected - filled_keys)
        if unfilled:
            raise StepFailed(f"autofill left {unfilled} empty (filled {sorted(filled_keys)})")
        return f"{len(fields)} fields detected, {len(filled)} filled from the profile"

    def _answer() -> str:
        application_id = state["application_id"]
        detail = smoke.get(f"/applications/{application_id}").json()
        pending = [a for a in detail.get("answers") or [] if a.get("status") == "NEEDS_USER_INPUT"]
        if not pending:
            return "nothing was left for the user"
        payload = [{"id": row["id"], "answer": _human_answer(row)} for row in pending]
        smoke.put(f"/applications/{application_id}/answers", json={"answers": payload})
        review = smoke.get(f"/applications/{application_id}/review").json()
        if not review.get("can_submit"):
            raise StepFailed(f"still blocked after answering: {review.get('blockers')}")
        return f"{len(pending)} answer(s) supplied, review clear"

    def _approve() -> str:
        application_id = state["application_id"]
        detail = smoke.post(f"/applications/{application_id}/approve").json()
        # The bundled demo ATS confirms in-process, so its "thank you" email can already have
        # moved the application past APPLIED by the time approve() returns. Both are correct.
        if detail["status"] not in ("APPLIED", "APPLICATION_RECEIVED"):
            raise StepFailed(f"status is {detail['status']}, expected APPLIED")
        if not detail.get("applied_at"):
            raise StepFailed("applied_at was not recorded")
        external = detail.get("external_application_id") or ""
        if not external.startswith("DEMO-"):
            raise StepFailed(f"external_application_id is {external!r}, expected DEMO-...")
        state["external_id"] = external
        return f"submitted as {external} (status {detail['status']})"

    def _confirmation_email() -> str:
        application_id = state["application_id"]
        deadline = time.monotonic() + 30
        email = None
        while time.monotonic() < deadline:
            body = smoke.get("/emails", params={"application_id": application_id}).json()
            candidates = [
                row for row in body.get("items") or [] if "thank you for applying" in (row.get("subject") or "").lower()
            ]
            if candidates:
                email = candidates[0]
                break
            time.sleep(1.0)
        if email is None:
            raise StepFailed("the simulated 'Thank you for applying' email never arrived")
        detail = smoke.get(f"/applications/{application_id}").json()
        if detail["status"] != "APPLICATION_RECEIVED":
            raise StepFailed(f"application status is {detail['status']}, expected APPLICATION_RECEIVED")
        return f"{email['classification']} email linked, status -> APPLICATION_RECEIVED"

    smoke.step("browser: queue a DEMO_ATS job", _queue)
    if "application_id" not in state:
        return
    smoke.step("browser: POST /applications/{id}/start and wait for the pause", _start)
    if "detail" not in state:
        return
    smoke.step("browser: form_snapshot has the expected fields", _snapshot)
    smoke.step("browser: PUT /applications/{id}/answers", _answer)
    smoke.step("browser: POST /applications/{id}/approve", _approve)
    smoke.step("browser: the ATS confirmation email arrives", _confirmation_email)


def _human_answer(answer: dict[str, Any]) -> str:
    """A plausible human answer for whatever the form asked that the profile cannot know."""
    key = str(answer.get("question_key") or "")
    text = f"{key} {answer.get('question_text') or ''}".lower()
    if "consent" in text:
        return "Yes"
    if "start" in text and "date" in text:
        return "1 December 2026"
    if "kubernetes" in text:
        return "I ran a three-node EKS cluster for our staging workloads for a year."
    if "salary" in text or "ctc" in text:
        return "1200000"
    return "Yes"


# --------------------------------------------------------------------------- entry point


def run(base_url: str, email: str, password: str, *, with_browser: bool, poll_seconds: float) -> Report:
    report = Report()
    smoke = Smoke(base_url, report)
    print(f"JobPilot AI smoke test against {base_url}\n", flush=True)
    try:
        smoke.step("GET /health", lambda: smoke.request("GET", f"{smoke.base_url}/health").json()["status"])
        token = smoke.step("POST /api/v1/auth/login", lambda: login(smoke, email, password))
        if token is None:
            report.record("smoke aborted", False, "cannot continue without a session")
            return report

        read_only_screens(smoke)
        demo_ats_pages(smoke)
        discover_jobs(smoke)
        automation_run(smoke, poll_seconds)
        simulate_email(smoke)

        if with_browser:
            available = smoke.get("/browser/status").json().get("available")
            if not available:
                report.record("browser path", False, "Chromium is not installed (python -m playwright install chromium)")
            else:
                browser_path(smoke, poll_seconds)
    finally:
        smoke.close()
    return report


def main(argv: list[str] | None = None) -> int:
    default_email, default_password = _default_credentials()
    parser = argparse.ArgumentParser(prog="smoke_e2e.py", description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"backend root URL (default {DEFAULT_BASE_URL})")
    parser.add_argument("--email", default=default_email, help="demo account email")
    parser.add_argument("--password", default=default_password, help="demo account password")
    parser.add_argument("--with-browser", action="store_true", help="also run the Playwright autofill path")
    parser.add_argument("--poll-seconds", type=float, default=90.0, help="how long to wait for async work")
    args = parser.parse_args(argv)

    report = run(
        args.base_url,
        args.email,
        args.password,
        with_browser=args.with_browser,
        poll_seconds=args.poll_seconds,
    )

    passed = len(report.steps) - report.failures
    print(f"\n{passed}/{len(report.steps)} steps passed", flush=True)
    if report.failures:
        print("FAILED steps:", flush=True)
        for line in report.steps:
            if line.startswith("FAIL"):
                print(f"  {line}", flush=True)
        return 1
    print("ALL STEPS PASSED", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
