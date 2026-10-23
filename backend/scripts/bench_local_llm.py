"""Bake-off of small local Ollama models on JobPilot's own AI tasks.

For every model it runs, through the real ``OllamaProvider.complete_json``:

* ``parse_resume`` (ParsedResume schema) on three resumes: the test sample, a second
  synthetic resume, and the owner's current default resume read **read-only** from the
  live database (the text never leaves this machine; it is only sent to localhost);
* ``classify_email`` on five short synthetic emails;
* the bullet rewrite used by ``resumes.apply.strengthen_bullet`` on the owner's bullets,
  counting how many rewrites pass ``apply.bullet_problem``.

It reports JSON validity, field accuracy against the rule-based parse (name, email,
phone, number of experience entries, skills overlap), email accuracy, bullet pass rate,
median latency, generation tokens/s and whether the model ran fully on the GPU. Every
model is unloaded (``keep_alive: 0``) before the next one loads, so two chat models are
never resident together.

Usage::

    cd backend
    ./.venv/Scripts/python.exe scripts/bench_local_llm.py qwen3:4b-instruct phi4-mini gemma3:4b
    ./.venv/Scripts/python.exe scripts/bench_local_llm.py --json out.json qwen2.5:3b-instruct

Nothing is written to the database.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.modules.ai import factory  # noqa: E402
from app.modules.ai.factory import get_mock_provider  # noqa: E402
from app.modules.ai.prompts import build_prompt, build_system_prompt  # noqa: E402
from app.modules.ai.providers.ollama import OllamaProvider, _same_model  # noqa: E402
from app.modules.ai.schemas import EmailClassificationResult, ParsedResume  # noqa: E402
from app.modules.ai.skills import normalize_skills  # noqa: E402

OWNER_EMAIL = "neerajmishra1085@gmail.com"

SECOND_RESUME = """Priya Nair
Kochi, India | priya.nair.dev@example.org | +91 99887 76655
github.com/priyanair

Summary
Backend engineer with 4 years of experience building Python and Go services.

Experience
Senior Backend Engineer - Lumen Payments
Kochi, India | Jan 2023 - Present
- Built a payment reconciliation service in Go and PostgreSQL.
- Moved batch jobs from cron to Celery and Redis queues.
- Reviewed pull requests and wrote the team's API style guide.

Backend Engineer, Orbit Logistics
Chennai, India | 06/2020 - 12/2022
- Developed Django REST APIs for shipment tracking.
- Wrote integration tests with pytest and Docker Compose.

Projects
RateLimiter - Token-bucket rate limiter for FastAPI, published on PyPI.
Technologies: Python, FastAPI, Redis

LogLens: a CLI that groups similar log lines with TF-IDF.

Skills
Python, Go, SQL,
Django, FastAPI, Celery,
PostgreSQL, Redis, Kafka,
Docker, Kubernetes, AWS

Education
B.E. in Information Technology - Anna University, Chennai
2016 - 2020
"""

EMAILS: list[tuple[str, dict[str, str]]] = [
    (
        "INTERVIEW",
        {
            "subject": "Interview invitation - Backend Engineer",
            "sender": "talent@acme.io",
            "body": "Hi Neeraj, thanks for applying. We would like to schedule a 45-minute technical interview "
            "with our engineering team next week. Please pick a slot using the link below.",
        },
    ),
    (
        "REJECTION",
        {
            "subject": "Your application to Globex",
            "sender": "no-reply@globex.com",
            "body": "Thank you for your interest in the Python Developer role. After careful consideration we "
            "have decided to move forward with other candidates. We wish you the best in your search.",
        },
    ),
    (
        "APPLICATION_RECEIVED",
        {
            "subject": "We received your application",
            "sender": "jobs@initech.com",
            "body": "Thanks for applying to the Full Stack Engineer position at Initech. Our team will review "
            "your application and get back to you if your profile matches.",
        },
    ),
    (
        "ASSESSMENT",
        {
            "subject": "Next step: online coding assessment",
            "sender": "hiring@hooli.com",
            "body": "Please complete the HackerRank coding assessment within 72 hours. It has three problems "
            "and takes about 90 minutes.",
        },
    ),
    (
        "RECRUITER_MESSAGE",
        {
            "subject": "Opportunity at a fintech startup",
            "sender": "anita@talentbridge.in",
            "body": "Hi, I am a recruiter at TalentBridge. I came across your profile and have a Senior React "
            "role with a Series B fintech client. Are you open to a quick call this week?",
        },
    ),
]


# --------------------------------------------------------------------------- owner data (read-only)


def load_owner() -> tuple[str, dict[str, Any], Any]:
    """``(text_content, parsed_data, MatchInputs)`` of the owner's default resume, read-only."""
    from sqlalchemy import select, text

    from app.core.database import SessionLocal
    from app.models.resume import Resume
    from app.models.user import User
    from app.modules.resumes import recommendations as rec_mod

    db = SessionLocal()
    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        user = db.scalars(select(User).where(User.email == OWNER_EMAIL)).first()
        if user is None:
            raise SystemExit(f"No user {OWNER_EMAIL}")
        resume = db.scalars(
            select(Resume)
            .where(Resume.user_id == user.id, Resume.is_default.is_(True), Resume.deleted_at.is_(None))
            .order_by(Resume.updated_at.desc())
        ).first()
        if resume is None or not resume.text_content:
            raise SystemExit("The owner has no default resume with text")
        inputs = rec_mod.load_match_inputs(db, user.id)
        return resume.text_content, dict(resume.parsed_data or {}), inputs
    finally:
        db.rollback()
        db.close()


# --------------------------------------------------------------------------- ollama helpers


def loaded_models(base: str) -> list[dict[str, Any]]:
    return httpx.get(f"{base}/api/ps", timeout=10).json().get("models") or []


def unload_all(base: str, keep: set[str] | None = None) -> None:
    for entry in loaded_models(base):
        name = entry.get("name") or entry.get("model")
        if keep and name in keep:
            continue
        httpx.post(f"{base}/api/generate", json={"model": name, "keep_alive": 0}, timeout=60)
    for _ in range(30):
        names = {m.get("name") for m in loaded_models(base)}
        if not names - (keep or set()):
            return
        time.sleep(0.5)


def model_size_on_disk(base: str, model: str) -> int | None:
    for entry in httpx.get(f"{base}/api/tags", timeout=10).json().get("models") or []:
        if _same_model(model, str(entry.get("name") or entry.get("model") or "")):
            return int(entry.get("size") or 0)
    return None


@dataclass
class Call:
    task: str
    seconds: float
    attempts: int
    valid: bool
    eval_count: int = 0
    eval_seconds: float = 0.0
    prompt_tokens: int = 0


@dataclass
class Result:
    model: str
    disk_bytes: int | None = None
    vram_bytes: int | None = None
    total_bytes: int | None = None
    load_seconds: float | None = None
    calls: list[Call] = field(default_factory=list)
    parse_scores: list[dict[str, float]] = field(default_factory=list)
    parse_labels: list[str] = field(default_factory=list)
    email_correct: int = 0
    email_total: int = 0
    bullets_passed: int = 0
    bullets_total: int = 0
    bullet_outputs: list[dict[str, Any]] = field(default_factory=list)
    replacement_chars: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def full_gpu(self) -> bool:
        return bool(self.total_bytes) and self.vram_bytes == self.total_bytes

    def summary(self) -> dict[str, Any]:
        valid = sum(1 for c in self.calls if c.valid)
        first = sum(1 for c in self.calls if c.valid and c.attempts == 1)
        evals = sum(c.eval_count for c in self.calls)
        eval_s = sum(c.eval_seconds for c in self.calls)
        fields = [statistics.mean(s.values()) for s in self.parse_scores] if self.parse_scores else [0.0]
        return {
            "model": self.model,
            "disk_gb": round((self.disk_bytes or 0) / 1e9, 2),
            "loaded_gb": round((self.total_bytes or 0) / 1e9, 2),
            "gpu": "100% GPU" if self.full_gpu else f"{round(100 * (self.vram_bytes or 0) / (self.total_bytes or 1))}% GPU",
            "load_s": round(self.load_seconds or 0, 1),
            "json_valid": f"{valid}/{len(self.calls)}",
            "json_valid_first_try": f"{first}/{len(self.calls)}",
            "field_accuracy": round(statistics.mean(fields), 3),
            "field_detail": dict(zip(self.parse_labels, self.parse_scores)),
            "email_accuracy": f"{self.email_correct}/{self.email_total}",
            "bullet_pass": f"{self.bullets_passed}/{self.bullets_total}",
            "median_latency_s": round(statistics.median(c.seconds for c in self.calls), 2) if self.calls else None,
            "median_parse_s": round(statistics.median(c.seconds for c in self.calls if c.task == "parse"), 2)
            if any(c.task == "parse" for c in self.calls)
            else None,
            "tok_per_s": round(evals / eval_s, 1) if eval_s else None,
            "max_prompt_tokens": max([c.prompt_tokens for c in self.calls] or [0]),
            "replacement_chars": self.replacement_chars,
            "errors": self.errors,
            "bullets": self.bullet_outputs,
        }


class Recorder:
    """Wraps the provider's HTTP client to read Ollama's timing fields per request."""

    def __init__(self, provider: OllamaProvider) -> None:
        self.responses: list[dict[str, Any]] = []
        original = provider._client.post

        def post(url: str, **kwargs: Any) -> httpx.Response:
            response = original(url, **kwargs)
            try:
                self.responses.append(response.json())
            except ValueError:
                self.responses.append({})
            return response

        provider._client.post = post  # type: ignore[method-assign]

    def take(self) -> list[dict[str, Any]]:
        out, self.responses = self.responses, []
        return out


def _timed(recorder: Recorder, task: str, fn) -> tuple[Any, Call]:
    recorder.take()
    start = time.perf_counter()
    error = None
    try:
        value = fn()
    except Exception as exc:  # noqa: BLE001 - recorded as an invalid call
        value, error = None, exc
    seconds = time.perf_counter() - start
    responses = recorder.take()
    call = Call(
        task=task,
        seconds=seconds,
        attempts=len(responses),
        valid=False,
        eval_count=sum(int(r.get("eval_count") or 0) for r in responses),
        eval_seconds=sum(int(r.get("eval_duration") or 0) for r in responses) / 1e9,
        prompt_tokens=max([int(r.get("prompt_eval_count") or 0) for r in responses] or [0]),
    )
    if error is not None:
        call.task = f"{task}:error:{error}"
    return value, call


# --------------------------------------------------------------------------- scoring


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def field_scores(rule: ParsedResume, llm: ParsedResume) -> dict[str, float]:
    rule_skills = {s.lower() for s in normalize_skills(rule.skills)}
    llm_skills = {s.lower() for s in normalize_skills([str(s) for s in llm.skills])}
    union = rule_skills | llm_skills
    return {
        "name": float((rule.name or "").strip().lower() == (llm.name or "").strip().lower()),
        "email": float((rule.email or "").strip().lower() == (llm.email or "").strip().lower()),
        "phone": float(_digits(rule.phone)[-10:] == _digits(llm.phone)[-10:]),
        "experience_count": float(len(rule.experience) == len(llm.experience)),
        "skills_jaccard": round(len(rule_skills & llm_skills) / len(union), 3) if union else 1.0,
    }


# --------------------------------------------------------------------------- bench


def bench_model(
    model: str,
    resumes: list[tuple[str, str]],
    bullets: list[str],
    entry: dict[str, Any],
    facts: Any,
    *,
    num_ctx: int | None = None,
) -> Result:
    from app.modules.resumes import apply as apply_mod

    base = settings.OLLAMA_BASE_URL.rstrip("/")
    label = f"{model} (ctx {num_ctx})" if num_ctx else model
    result = Result(model=label, disk_bytes=model_size_on_disk(base, model))
    unload_all(base, keep={settings.EMBEDDING_MODEL} if hasattr(settings, "EMBEDDING_MODEL") else None)

    provider = OllamaProvider(model=model, keep_alive="5m", num_ctx=num_ctx)
    recorder = Recorder(provider)
    factory._provider = provider  # apply._llm_bullet reads the process-wide provider
    try:
        start = time.perf_counter()
        provider.complete("Say OK.", max_tokens=4)
        recorder.take()
        result.load_seconds = time.perf_counter() - start
        for entry_ps in loaded_models(base):
            if _same_model(model, str(entry_ps.get("name") or entry_ps.get("model") or "")):
                result.vram_bytes = int(entry_ps.get("size_vram") or 0)
                result.total_bytes = int(entry_ps.get("size") or 0)

        mock = get_mock_provider()
        for label, text in resumes:
            payload = {"text": text[:40_000]}
            rule = ParsedResume.model_validate(mock.run_task("parse_resume", payload))
            prompt = build_prompt("parse_resume", payload, schema=ParsedResume)
            data, call = _timed(
                recorder,
                "parse",
                lambda: provider.complete_json(prompt, schema=ParsedResume, system=build_system_prompt("parse_resume")),
            )
            try:
                llm = ParsedResume.model_validate(data)
                call.valid = isinstance(data, dict) and bool(data)
            except Exception as exc:  # noqa: BLE001
                llm = ParsedResume()
                result.errors.append(f"parse {label}: {exc}"[:200])
            result.calls.append(call)
            if "\ufffd" in json.dumps(data or {}, ensure_ascii=False):
                result.replacement_chars += 1
            scores = field_scores(rule, llm) if call.valid else dict.fromkeys(
                ("name", "email", "phone", "experience_count", "skills_jaccard"), 0.0
            )
            result.parse_scores.append(scores)
            result.parse_labels.append(label)

        for expected, email in EMAILS:
            prompt = build_prompt("classify_email", email, schema=EmailClassificationResult)
            data, call = _timed(
                recorder,
                "email",
                lambda: provider.complete_json(
                    prompt, schema=EmailClassificationResult, system=build_system_prompt("classify_email")
                ),
            )
            try:
                parsed = EmailClassificationResult.model_validate(data)
                call.valid = True
                result.email_correct += int(parsed.classification.value == expected)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"email {expected}: {exc}"[:200])
            result.email_total += 1
            result.calls.append(call)

        for bullet in bullets:
            text, call = _timed(recorder, "bullet", lambda: apply_mod._llm_bullet(bullet, entry))
            call.valid = bool(text)
            result.calls.append(call)
            problem = apply_mod.bullet_problem(text, bullet, facts) if text else "no_output"
            if text and "\ufffd" in text:
                result.replacement_chars += 1
            result.bullets_total += 1
            result.bullets_passed += int(problem is None)
            result.bullet_outputs.append({"original": bullet, "rewrite": text, "problem": problem})
    finally:
        factory._provider = None
        httpx.post(f"{base}/api/generate", json={"model": model, "keep_alive": 0}, timeout=60)
        provider.close()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("models", nargs="+")
    parser.add_argument("--json", help="write the full results to this file")
    parser.add_argument("--num-ctx", type=int, default=None, help="context window (default: OLLAMA_NUM_CTX)")
    args = parser.parse_args(argv)

    from tests.helpers.documents import SAMPLE_RESUME_TEXT
    from app.modules.resumes import apply as apply_mod
    from app.modules.resumes.recommendations import split_bullets

    owner_text, owner_parsed, inputs = load_owner()
    experience = owner_parsed.get("experience") or [{}]
    entry = experience[0]
    bullets = split_bullets(entry.get("description"))[:6]
    facts = apply_mod._Facts(parsed=owner_parsed, raw_text=owner_text, inputs=inputs)
    resumes = [("sample", SAMPLE_RESUME_TEXT), ("synthetic", SECOND_RESUME), ("owner", owner_text)]

    summaries = []
    for model in args.models:
        print(f"== {model}", flush=True)
        result = bench_model(model, resumes, bullets, entry, facts, num_ctx=args.num_ctx)
        summary = result.summary()
        summaries.append(summary)
        print(json.dumps({k: v for k, v in summary.items() if k not in {"bullets", "field_detail"}}, ensure_ascii=False), flush=True)

    header = ("model", "disk_gb", "gpu", "json_valid", "field_accuracy", "email_accuracy", "bullet_pass", "median_latency_s", "median_parse_s", "tok_per_s")
    print("\n" + " | ".join(header))
    for s in summaries:
        print(" | ".join(str(s[h]) for h in header))
    if args.json:
        Path(args.json).write_text(json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
