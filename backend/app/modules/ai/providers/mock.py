"""Deterministic, rule-based provider — the default in development, tests and the demo.

The mock never calls a network service: every task is answered by explicit rules and
templates over the *structured* payload it is given. That has three benefits:

* the whole product (including the Playwright demo) runs with no API key;
* tests are fully deterministic — the same payload always yields the same output;
* the "never invent facts" rule is enforced in code, not by prompt-wishing.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel

from app.models.enums import AnswerSource, EmailClassification
from app.modules.ai import answer_rules as rules
from app.modules.ai.prompts import parse_task_envelope
from app.modules.ai.provider import LLMProvider
from app.modules.ai.resume_parser import parse_resume_text
from app.modules.ai.skills import normalize_skills

logger = logging.getLogger(__name__)

MAX_COVER_LETTER_WORDS = 250

TASK_NAMES: frozenset[str] = frozenset(
    {
        "parse_resume",
        "explain_match",
        "generate_answer",
        "generate_cover_letter",
        "classify_email",
        "generate_interview_prep",
        "polish_resume_recommendations",
    }
)

# --------------------------------------------------------------------------- email rules
# (classification, weight, keywords). Subject/sender hits count double.
_EMAIL_RULES: tuple[tuple[EmailClassification, int, tuple[str, ...]], ...] = (
    (
        EmailClassification.OFFER,
        3,
        ("offer letter", "pleased to offer", "happy to offer", "delighted to offer", "job offer", "compensation details", "offer of employment"),
    ),
    (
        EmailClassification.REJECTION,
        3,
        (
            "unfortunately",
            "not moving forward",
            "not move forward",
            "regret to inform",
            "we regret",
            "other candidates",
            "decided to proceed with other",
            "not selected",
            "was not successful",
            "no longer under consideration",
        ),
    ),
    (
        EmailClassification.ASSESSMENT,
        3,
        (
            "assessment",
            "coding challenge",
            "coding test",
            "hackerrank",
            "codility",
            "codesignal",
            "take-home",
            "take home",
            "online test",
            "test link",
            "aptitude test",
        ),
    ),
    (
        EmailClassification.INTERVIEW,
        3,
        (
            "interview",
            "schedule a call",
            "availability",
            "available for a call",
            "book a slot",
            "calendar invite",
            "technical round",
            "meet the team",
            "next round",
        ),
    ),
    (
        EmailClassification.RECRUITER_MESSAGE,
        2,
        ("recruiter", "reaching out", "reached out", "opportunity", "your profile", "came across your", "talent acquisition", "hiring for"),
    ),
    (
        EmailClassification.APPLICATION_RECEIVED,
        2,
        (
            "application received",
            "we received your application",
            "we have received your application",
            "thank you for applying",
            "thanks for applying",
            "your application has been received",
            "application submitted",
            "we received your",
        ),
    ),
)

# Domains that never identify the hiring company.
_GENERIC_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "icloud.com",
        "protonmail.com",
        "greenhouse.io",
        "us.greenhouse-mail.io",
        "greenhouse-mail.io",
        "lever.co",
        "hire.lever.co",
        "myworkday.com",
        "workday.com",
        "smartrecruiters.com",
        "naukri.com",
        "linkedin.com",
        "indeed.com",
        "glassdoor.com",
        "foundit.in",
        "hirist.com",
        "wellfound.com",
        "internshala.com",
        "jobpilot.ai",
        "example.com",
        "mail.com",
    }
)

_TITLE_HINT_RES = (
    re.compile(r"application for (?:the )?(?P<title>[A-Za-z0-9 /+#.&-]{3,60}?)\s*(?:role|position|job|opening|\(|-|–|—|at\b|$)", re.IGNORECASE),
    re.compile(r"(?:for|regarding|re:)\s+(?:the )?(?P<title>[A-Za-z0-9 /+#.&-]{3,60}?)\s+(?:role|position|opening)\b", re.IGNORECASE),
    re.compile(r"^(?P<title>[A-Za-z0-9 /+#.&-]{3,60}?)\s+(?:role|position)\s+at\b", re.IGNORECASE),
)

_COMPANY_HINT_RES = (
    re.compile(r"\bat\s+(?P<company>[A-Z][A-Za-z0-9&.\- ]{1,40}?)(?:\s*[-–—|,.!]|$)"),
    re.compile(r"\bfrom\s+(?P<company>[A-Z][A-Za-z0-9&.\- ]{1,40}?)(?:\s*[-–—|,.!]|$)"),
)

# --------------------------------------------------------------------------- prep banks

_SKILL_QUESTION_BANK: dict[str, tuple[str, ...]] = {
    "React": ("How do you decide between local state, context and a store in a React app?", "What causes unnecessary re-renders in React and how do you find them?"),
    "Node.js": ("How would you debug an event-loop stall in a Node.js service?", "How do you handle backpressure when streaming data in Node.js?"),
    "TypeScript": ("When do you reach for generics over `any` in TypeScript, and why?", "How do you type an API response you do not control?"),
    "JavaScript": ("Explain the difference between `==`, `===` and `Object.is` with an example.", "How do closures help (and hurt) in asynchronous JavaScript?"),
    "Python": ("How do you profile and speed up a slow Python endpoint?", "Explain the difference between threads, processes and asyncio in Python."),
    "PostgreSQL": ("Walk through how you would diagnose a slow PostgreSQL query.", "When would you add a partial or composite index, and what does it cost?"),
    "MongoDB": ("How do you model a one-to-many relationship in MongoDB, and when does it break down?",),
    "Redis": ("What would you cache in Redis for this product, and how would you invalidate it?",),
    "Docker": ("How do you keep a production Docker image small and reproducible?",),
    "Kubernetes": ("What happens, step by step, when a pod fails its readiness probe?",),
    "AWS": ("Which AWS services would you use for a background job queue, and why?",),
    "GraphQL": ("How do you prevent N+1 queries behind a GraphQL resolver?",),
    "REST APIs": ("How do you version a REST API without breaking existing clients?",),
    "System Design": ("Design a URL shortener that serves 10k requests per second. Where does it break first?",),
    "Microservices": ("How do you keep data consistent across two services without distributed transactions?",),
    "Kafka": ("How do you guarantee at-least-once processing with Kafka consumers?",),
    "CI/CD": ("What does your ideal CI pipeline run before a merge is allowed?",),
    "Django": ("How do you avoid N+1 queries with the Django ORM?",),
    "FastAPI": ("How do you structure dependency injection and testing in a FastAPI service?",),
    "Java": ("Explain how you would tune garbage collection for a latency-sensitive service.",),
    "Go": ("How do goroutines and channels change the way you structure concurrent work?",),
}

_BEHAVIORAL_BANK: tuple[str, ...] = (
    "Tell me about a time you disagreed with a technical decision. What did you do?",
    "Describe a production incident you were part of. What was your role and what changed afterwards?",
    "Tell me about a deadline you were not going to meet. How did you handle it?",
    "Describe feedback that was hard to hear and what you did with it.",
    "Tell me about something you shipped that you would build differently today.",
    "How do you decide what to work on when everything is marked urgent?",
    "Describe a time you had to learn an unfamiliar technology quickly.",
)


def _first_sentence(text: str | None, limit: int = 180) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return None
    match = re.search(r"^(.{20,%d}?[.!?])\s" % limit, cleaned + " ")
    sentence = match.group(1) if match else cleaned[:limit]
    return sentence.strip().rstrip(".") or None


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _format_number(value: Any) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _word_limit(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    clipped = " ".join(words[:max_words])
    cut = max(clipped.rfind("."), clipped.rfind("!"), clipped.rfind("?"))
    if cut > len(clipped) // 2:
        return clipped[: cut + 1]
    return clipped.rstrip(",;: ") + "."


class MockLLMProvider(LLMProvider):
    """Rule/template based provider. Deterministic for a given payload."""

    name = "mock"
    model = "mock-deterministic-v1"
    is_deterministic = True

    # ------------------------------------------------------------------ API

    def supports_task(self, task_name: str) -> bool:
        return task_name in TASK_NAMES

    def run_task(self, task_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        handler = {
            "parse_resume": self._parse_resume,
            "explain_match": self._explain_match,
            "generate_answer": self._generate_answer,
            "generate_cover_letter": self._generate_cover_letter,
            "classify_email": self._classify_email,
            "generate_interview_prep": self._generate_interview_prep,
            "polish_resume_recommendations": self._polish_resume_recommendations,
        }.get(task_name)
        if handler is None:
            raise NotImplementedError(f"MockLLMProvider cannot run task {task_name!r}")
        return handler(payload or {})

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.2,
    ) -> str:
        result = self._dispatch_prompt(prompt)
        if result is None:
            return ""
        for key in ("explanation", "cover_letter", "answer", "text"):
            if isinstance(result.get(key), str):
                return result[key]
        return json.dumps(result, ensure_ascii=False, default=str)

    def complete_json(
        self,
        prompt: str,
        *,
        schema: dict[str, Any] | type[BaseModel] | None = None,
        system: str | None = None,
        max_tokens: int = 1500,
    ) -> dict[str, Any]:
        return self._dispatch_prompt(prompt) or {}

    def _dispatch_prompt(self, prompt: str) -> dict[str, Any] | None:
        envelope = parse_task_envelope(prompt)
        if envelope is None:
            logger.debug("Mock provider received a prompt without a task envelope")
            return None
        task_name, payload = envelope
        if not self.supports_task(task_name):
            return None
        return self.run_task(task_name, payload)

    # ------------------------------------------------------------------ tasks

    def _parse_resume(self, payload: dict[str, Any]) -> dict[str, Any]:
        return parse_resume_text(payload.get("text") or "")

    # -- match explanation -------------------------------------------------

    def _explain_match(self, payload: dict[str, Any]) -> dict[str, Any]:
        job = payload.get("job") or {}
        scores = payload.get("scores") or {}
        candidate = payload.get("candidate") or {}

        title = job.get("title") or "this role"
        company = job.get("company_name") or "the company"
        priority = str(scores.get("company_priority") or "").upper()

        if priority == "AVOID":
            return {"explanation": "Company is on your avoid list"}

        skill_match = scores.get("skill_match") or {}
        matched = [str(s) for s in _as_list(skill_match.get("matched"))]
        missing = [str(s) for s in _as_list(skill_match.get("missing") or scores.get("missing_skills"))]
        total = skill_match.get("total") or (len(matched) + len(missing))

        sentences: list[str] = []
        overall = scores.get("match_score")
        if overall is not None:
            sentences.append(f"{title} at {company} scores {int(overall)}/100 against your profile.")
        else:
            sentences.append(f"{title} at {company} was compared against your profile.")

        if matched or missing:
            head = f"You match {len(matched)} of {total or len(matched)} required skills"
            if matched:
                head += f" ({', '.join(matched[:4])})"
            if missing:
                head += f", and the posting also asks for {', '.join(missing[:3])}"
            sentences.append(head + ".")

        experience_fit = str(scores.get("experience_match") or "").upper()
        years = candidate.get("years_of_experience")
        span = _experience_span(job)
        experience_sentence = {
            "STRONG": f"Your {years} years of experience sit comfortably in the {span} the role asks for." if years and span else "Your experience is a strong fit for the role.",
            "GOOD": f"Your experience is close to the {span} requested." if span else "Your experience is close to what the role requests.",
            "UNDER": f"The role asks for {span}, which is above your current experience." if span else "The role asks for more experience than your profile shows.",
            "OVER": f"You are more experienced than the {span} the role targets." if span else "You are more experienced than this role targets.",
        }.get(experience_fit)
        if experience_sentence:
            sentences.append(experience_sentence)

        location_fit = str(scores.get("location_match") or "").upper()
        location_sentence = {
            "MATCH": f"The location ({job.get('location')}) is one of your preferred places to work." if job.get("location") else "The location matches your preferences.",
            "REMOTE_OK": "It is remote friendly, which fits your preferences.",
            "MISMATCH": f"The location ({job.get('location')}) is outside your preferred locations." if job.get("location") else "The location is outside your preferred locations.",
        }.get(location_fit)
        if location_sentence:
            sentences.append(location_sentence)

        salary_fit = str(scores.get("salary_match") or "").upper()
        salary_sentence = {
            "ABOVE": "The advertised salary is above your expectation.",
            "WITHIN": "The advertised salary is within your expected range.",
            "BELOW": "The advertised salary is below your expectation.",
        }.get(salary_fit)
        if salary_sentence:
            sentences.append(salary_sentence)

        if priority == "P1":
            sentences.append(f"{company} is on your priority list.")

        explanation = " ".join(sentences[:4])
        return {"explanation": explanation}

    # -- answers -----------------------------------------------------------

    def _generate_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        question = str(payload.get("question") or "").strip()
        field_type = str(payload.get("field_type") or "TEXT").upper()
        options = [str(o) for o in _as_list(payload.get("options")) if str(o).strip()]
        job = payload.get("job") or {}
        candidate = payload.get("candidate") or {}
        flat: dict[str, Any] = dict(candidate.get("flat") or {})

        key = payload.get("question_key") or rules.infer_question_key(question, field_type)
        sensitive = rules.is_sensitive_question(question, key)

        if key == "work_authorization":
            return self._work_authorization_answer(question, options, job, flat, key)

        stored, stored_key = _flat_lookup(flat, key)
        if stored is not None:
            return self._answer_from_fact(stored, stored_key, key, field_type, options, sensitive)

        if sensitive:
            return _needs_input(
                key,
                f"Not found in profile: {key}. Sensitive questions (eligibility, sponsorship, demographics) are never answered by AI.",
                sensitive=True,
            )

        intent = rules.free_text_intent(question)
        if intent:
            return self._composed_answer(intent[0], key, job, candidate, question)

        if key.startswith("custom:"):
            return _needs_input(key, f"Not found in profile: {key}. This question has no stored answer or template.")

        return _needs_input(key, f"Not found in profile: {key}")

    def _work_authorization_answer(
        self,
        question: str,
        options: list[str],
        job: dict[str, Any],
        flat: dict[str, Any],
        key: str,
    ) -> dict[str, Any]:
        country = rules.infer_country(question) or rules.infer_country(job.get("location"), job.get("company_name"))
        authorization = flat.get("work_authorization")
        allowed = rules.lookup_authorization(authorization, country)
        if allowed is None and isinstance(authorization, bool):
            allowed = authorization
        if allowed is None:
            return _needs_input(
                key,
                f"Not found in profile: work_authorization for {rules.country_display(country)}",
                sensitive=True,
            )
        answer = "Yes" if allowed else "No"
        if options:
            mapped = rules.match_option(allowed, options)
            if mapped is None:
                return _needs_input(key, "Could not map your work authorization onto the available options.", sensitive=True)
            answer = mapped
        return {
            "answer": answer,
            "source": AnswerSource.PROFILE.value,
            "confidence": 0.95,
            "rationale": f"From your profile: work authorization for {rules.country_display(country)}.",
            "needs_user_input": False,
            "question_key": key,
            "is_sensitive": True,
        }

    def _answer_from_fact(
        self,
        value: Any,
        stored_key: str,
        key: str,
        field_type: str,
        options: list[str],
        sensitive: bool,
    ) -> dict[str, Any]:
        if options:
            mapped = rules.match_option(value, options)
            if mapped is None:
                return _needs_input(
                    key,
                    f"Your profile value for {stored_key} does not map onto any of the available options.",
                    sensitive=sensitive,
                )
            answer = mapped
        else:
            answer = _render_fact(value, key, field_type)
        if not answer:
            return _needs_input(key, f"Not found in profile: {key}", sensitive=sensitive)
        return {
            "answer": answer,
            "source": rules.answer_source_for_key(stored_key),
            "confidence": 0.95 if stored_key.lower() == key.lower() else 0.85,
            "rationale": f"From your profile: {stored_key}.",
            "needs_user_input": False,
            "question_key": key,
            "is_sensitive": sensitive,
        }

    def _composed_answer(
        self,
        intent: str,
        key: str,
        job: dict[str, Any],
        candidate: dict[str, Any],
        question: str,
    ) -> dict[str, Any]:
        if intent == "cover_letter":
            text = self._generate_cover_letter({"job": job, "candidate": candidate})["cover_letter"]
        elif intent == "why_us":
            text = _compose_why_us(job, candidate)
        elif intent == "project":
            text = _compose_project(job, candidate)
        elif intent == "strengths":
            text = _compose_strengths(job, candidate)
        elif intent == "motivation":
            text = _compose_motivation(job, candidate)
        else:  # pragma: no cover - defensive
            text = ""
        if not text:
            return _needs_input(key, f"Not found in profile: {key}. There is not enough profile context to compose an answer.")
        return {
            "answer": text,
            "source": AnswerSource.AI_GENERATED.value,
            "confidence": 0.7,
            "rationale": "Composed from your profile, resume and this job posting (no new facts added).",
            "needs_user_input": False,
            "question_key": key,
            "is_sensitive": False,
        }

    # -- cover letter ------------------------------------------------------

    def _generate_cover_letter(self, payload: dict[str, Any]) -> dict[str, Any]:
        job = payload.get("job") or {}
        candidate = payload.get("candidate") or {}
        company = job.get("company_name") or "your team"
        title = job.get("title") or "this role"
        name = candidate.get("full_name") or (candidate.get("flat") or {}).get("full_name")
        years = candidate.get("years_of_experience")
        headline = candidate.get("headline") or candidate.get("current_designation")
        current_company = candidate.get("current_company")
        top_skills = _top_matching_skills(job, candidate, limit=4)

        paragraphs: list[str] = [f"Dear {company} Hiring Team,"]

        opening = f"I am writing to apply for the {title} role at {company}."
        if headline and years:
            opening += f" I am a {headline} with {_format_number(years)} years of professional experience."
        elif headline:
            opening += f" I currently work as a {headline}."
        elif years:
            opening += f" I have {_format_number(years)} years of professional experience."
        paragraphs.append(opening)

        body: list[str] = []
        if top_skills:
            body.append(f"My day-to-day work is built on {_join(top_skills)}, which is what this role calls for.")
        if current_company:
            body.append(f"At {current_company} I own features end to end, from design through release and support.")
        project = _first_project(candidate)
        if project:
            tech = _join([str(t) for t in _as_list(project.get("technologies"))[:3]])
            body.append(
                f"One example is {project.get('name')}" + (f", built with {tech}." if tech else ".")
            )
        if body:
            paragraphs.append(" ".join(body))

        closing = f"I would welcome the chance to discuss how I can contribute to {company}."
        paragraphs.append(closing)
        paragraphs.append("Thank you for your time." + (f"\n\n{name}" if name else ""))

        letter = _word_limit("\n\n".join(paragraphs), MAX_COVER_LETTER_WORDS)
        return {"cover_letter": letter}

    # -- email classification ---------------------------------------------

    def _classify_email(self, payload: dict[str, Any]) -> dict[str, Any]:
        subject = str(payload.get("subject") or "")
        sender = str(payload.get("sender") or "")
        body = str(payload.get("body") or "")
        subject_l, sender_l, body_l = subject.lower(), sender.lower(), body.lower()

        scores: dict[EmailClassification, int] = {}
        hits: dict[EmailClassification, list[str]] = {}
        for classification, weight, keywords in _EMAIL_RULES:
            for keyword in keywords:
                found = 0
                if keyword in subject_l:
                    found += 2 * weight
                if keyword in sender_l:
                    found += weight
                if keyword in body_l:
                    found += weight
                if found:
                    scores[classification] = scores.get(classification, 0) + found
                    hits.setdefault(classification, []).append(keyword)

        if not scores:
            return {
                "classification": EmailClassification.OTHER.value,
                "confidence": 0.4,
                "reason": "No recruiting keywords matched in the subject, sender or body.",
                "company_hint": _company_hint(sender, subject),
                "job_title_hint": _job_title_hint(subject),
            }

        priority = [rule[0] for rule in _EMAIL_RULES]
        best = max(scores.items(), key=lambda item: (item[1], -priority.index(item[0])))
        classification, score = best
        confidence = round(min(0.95, 0.55 + 0.08 * score), 2)
        matched = ", ".join(sorted(set(hits.get(classification, [])))[:3])
        return {
            "classification": classification.value,
            "confidence": confidence,
            "reason": f"Matched {classification.value.replace('_', ' ').lower()} keywords: {matched}.",
            "company_hint": _company_hint(sender, subject),
            "job_title_hint": _job_title_hint(subject),
        }

    # -- interview prep ----------------------------------------------------

    def _generate_interview_prep(self, payload: dict[str, Any]) -> dict[str, Any]:
        job = payload.get("job") or {}
        candidate = payload.get("candidate") or {}
        interview_type = str(payload.get("interview_type") or "TECHNICAL").upper()
        title = job.get("title") or "the role"
        company = job.get("company_name") or "the company"

        job_skills = normalize_skills([str(s) for s in _as_list(job.get("required_skills")) + _as_list(job.get("preferred_skills"))])
        candidate_skills = normalize_skills([str(s) for s in _as_list(candidate.get("skills"))])

        technical: list[str] = []
        for skill in job_skills[:6]:
            bank = _SKILL_QUESTION_BANK.get(skill)
            if bank:
                technical.extend(bank)
            else:
                technical.append(f"Where have you used {skill}, and what went wrong the first time?")
        if interview_type in {"SYSTEM_DESIGN", "ONSITE"}:
            technical.append(f"Design the core service behind {title}. What are the read and write paths?")
            technical.append("How would you scale that design ten times without rewriting it?")
        if interview_type in {"ASSESSMENT", "TECHNICAL", "ONSITE"}:
            technical.append("Given a large log file, find the top N most frequent entries. What is the complexity?")
        if not technical:
            # the posting lists no skills — stay generic rather than inventing requirements
            technical = [
                f"Walk through the last thing you built that is closest to the {title} role.",
                "How do you decide a piece of code is ready to review?",
                "How do you debug a problem that only shows up in production?",
                "What does a good test suite look like for the work you do?",
            ]
        technical = _dedupe(technical)[:8]

        behavioral = list(_BEHAVIORAL_BANK)
        if interview_type in {"HR", "BEHAVIORAL", "PHONE_SCREEN"}:
            behavioral.append("Why are you looking to move from your current role?")
            behavioral.append("What does your ideal first 90 days here look like?")
        behavioral = _dedupe(behavioral)[:8]

        company_specific = [
            f"What do you know about {company} and the products the team works on?",
            f"Why {company} rather than another company hiring for the same role?",
            f"Which part of {company}'s stack would you want to work on first?",
            f"What would you want to ask a {company} engineer about day-to-day work?",
        ]
        description = _first_sentence(job.get("company_description"))
        if description:
            company_specific.insert(1, f"The posting describes {company} as \"{description}\". How does that fit what you are looking for?")
        company_specific = _dedupe(company_specific)[:6]

        job_specific = [f"Walk through how you would approach the main responsibility of the {title} role."]
        for skill in job_skills[:4]:
            job_specific.append(f"The posting lists {skill}. How current is your experience with it?")
        span = _experience_span(job)
        if span:
            job_specific.append(f"The role targets {span}. Where do you place yourself and why?")
        if job.get("location") or job.get("work_mode"):
            place = job.get("location") or str(job.get("work_mode")).title()
            job_specific.append(f"The role is based in {place}. Does that work for you long term?")
        missing = [s for s in job_skills if s not in set(candidate_skills)][:3]
        if missing:
            job_specific.append(f"How would you get up to speed on {_join(missing)} in the first month?")
        job_specific = _dedupe(job_specific)[:8]

        resume_based: list[str] = []
        for project in _as_list(candidate.get("projects"))[:3]:
            if not isinstance(project, dict) or not project.get("name"):
                continue
            tech = _join([str(t) for t in _as_list(project.get("technologies"))[:3]])
            resume_based.append(
                f"Your resume mentions the project {project['name']}"
                + (f" built with {tech}. What was the hardest part?" if tech else ". What was the hardest part?")
            )
        for entry in _as_list(candidate.get("experience"))[:3]:
            if not isinstance(entry, dict):
                continue
            role = entry.get("title") or "your role"
            employer = entry.get("company")
            resume_based.append(
                f"As {role}" + (f" at {employer}" if employer else "") + ", what was the change you are proudest of and why?"
            )
        for skill in candidate_skills[:2]:
            resume_based.append(f"You list {skill} on your resume. Talk me through the last thing you built with it.")
        resume_based = _dedupe(resume_based)[:8]

        return {
            "technical": technical,
            "behavioral": behavioral,
            "company_specific": company_specific,
            "job_specific": job_specific,
            "resume_based": resume_based,
        }


    # -- resume recommendations ----------------------------------------------

    def _polish_resume_recommendations(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Keep the rule-based wording and draft paste-ready text from resume facts only.

        Numbers the resume does not contain are never written: outcomes the candidate
        has to supply appear as bracketed placeholders.
        """
        resume = payload.get("resume") or {}
        items: list[dict[str, Any]] = []
        for rec in _as_list(payload.get("recommendations")):
            if not isinstance(rec, dict) or not rec.get("id"):
                continue
            category = str(rec.get("category") or "")
            suggested: str | None = None
            if category == "WEAK_SUMMARY":
                suggested = _draft_summary(resume)
            elif category == "EXPERIENCE_BULLETS":
                suggested = _draft_bullet(rec, resume)
            items.append({"id": rec["id"], "detail": rec.get("detail"), "suggested_text": suggested})
        return {"items": items}


# --------------------------------------------------------------------------- module helpers


def _draft_summary(resume: dict[str, Any]) -> str | None:
    """A summary assembled only from the resume's own title, years, skills and employer."""
    title = resume.get("recent_title")
    years = resume.get("total_experience_years")
    skills = [str(s) for s in _as_list(resume.get("summary_skills")) or _as_list(resume.get("skills"))][:3]
    experience = [e for e in _as_list(resume.get("experience")) if isinstance(e, dict)]
    company = experience[0].get("company") if experience else None
    if not (title or skills):
        return None
    opening = title or "Engineer"
    if years:
        opening += f" with {_format_number(years)} years of experience"
    if skills:
        opening += (" building with " if years else " working with ") + _join(skills)
    sentences = [_as_sentence(opening)]
    if company:
        sentences.append(f"Currently at {company}, delivering [the outcome you are proudest of].")
    target = resume.get("target_title")
    if target and title and str(target).strip().lower() != str(title).strip().lower():
        sentences.append(f"Looking for {target} roles.")
    return " ".join(sentences)


def _draft_bullet(rec: dict[str, Any], resume: dict[str, Any]) -> str | None:
    """Rewrite one weak bullet with an outcome placeholder, or sketch the missing bullets."""
    for item in _as_list(rec.get("evidence")):
        if isinstance(item, dict) and str(item.get("field") or "").endswith(".bullet") and item.get("label"):
            bullet = str(item["label"]).strip().rstrip(".")
            return f"{bullet}, resulting in [measurable outcome, e.g. X% faster or N more users]."
    for item in _as_list(rec.get("evidence")):
        if isinstance(item, dict) and str(item.get("field") or "").startswith("experience["):
            return "[Action verb] [what you built or changed] using [tools], resulting in [measurable outcome]."
    return None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if item.strip() and key not in seen:
            seen.add(key)
            out.append(item.strip())
    return out


def _as_sentence(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def _join(items: list[str]) -> str:
    cleaned = [i for i in items if i]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    return ", ".join(cleaned[:-1]) + f" and {cleaned[-1]}"


def _needs_input(key: str, rationale: str, *, sensitive: bool = False) -> dict[str, Any]:
    return {
        "answer": None,
        "source": AnswerSource.DEFAULT.value,
        "confidence": 0.0,
        "rationale": rationale,
        "needs_user_input": True,
        "question_key": key,
        "is_sensitive": sensitive,
    }


def _flat_lookup(flat: dict[str, Any], key: str) -> tuple[Any, str]:
    """Look a canonical key up in ``candidate.flat`` (with documented fallbacks)."""
    candidates = [key, key.lower()]
    if key.startswith("skill_years:"):
        skill = key.split(":", 1)[1]
        candidates += [f"skill_years:{skill.lower()}", f"skill_years:{skill.title()}"]
    candidates += list(rules.KEY_FALLBACKS.get(key, ()))
    lowered = {str(k).lower(): k for k in flat}
    for candidate in candidates:
        actual = lowered.get(candidate.lower())
        if actual is None:
            continue
        value = flat[actual]
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        return value, str(actual)
    return None, key


def _render_fact(value: Any, key: str, field_type: str) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value if str(v).strip())
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if key == "notice_period_days" and isinstance(value, (int, float)) and field_type != "NUMBER":
        days = int(value)
        return "Immediate" if days == 0 else f"{days} days"
    return _format_number(value)


def _experience_span(job: dict[str, Any]) -> str | None:
    low, high = job.get("experience_min"), job.get("experience_max")
    if low is not None and high is not None:
        return f"{_format_number(low)}-{_format_number(high)} years"
    if low is not None:
        return f"{_format_number(low)}+ years"
    if high is not None:
        return f"up to {_format_number(high)} years"
    return None


def _top_matching_skills(job: dict[str, Any], candidate: dict[str, Any], *, limit: int = 4) -> list[str]:
    job_skills = normalize_skills([str(s) for s in _as_list(job.get("required_skills")) + _as_list(job.get("preferred_skills"))])
    candidate_skills = normalize_skills([str(s) for s in _as_list(candidate.get("skills"))])
    candidate_set = {s.lower() for s in candidate_skills}
    matched = [s for s in job_skills if s.lower() in candidate_set]
    if matched:
        return matched[:limit]
    return candidate_skills[:limit]


def _first_project(candidate: dict[str, Any]) -> dict[str, Any] | None:
    for project in _as_list(candidate.get("projects")):
        if isinstance(project, dict) and project.get("name"):
            return project
    return None


def _compose_why_us(job: dict[str, Any], candidate: dict[str, Any]) -> str:
    company = job.get("company_name") or "your company"
    title = job.get("title") or "this role"
    headline = candidate.get("headline") or candidate.get("current_designation")
    years = candidate.get("years_of_experience")
    skills = _top_matching_skills(job, candidate, limit=4)
    if not any([headline, years, skills]):
        return ""

    sentences = []
    opening = f"I am interested in the {title} role at {company} because it matches the work I already do"
    opening += f" as a {headline}." if headline else "."
    sentences.append(opening)
    if skills:
        sentences.append(f"I work with {_join(skills)} day to day, which is the core of what this role asks for.")
    if years:
        sentences.append(f"With {_format_number(years)} years of professional experience, I can contribute without a long ramp-up.")
    description = _first_sentence(job.get("company_description"))
    if description:
        sentences.append(f"The posting describes {company} as \"{description}\", and that is the kind of product work I want to keep doing.")
    else:
        sentences.append(f"I would like to bring that experience to {company} and keep growing with the team.")
    return " ".join(sentences)


def _compose_project(job: dict[str, Any], candidate: dict[str, Any]) -> str:
    project = _first_project(candidate)
    if project:
        tech = [str(t) for t in _as_list(project.get("technologies"))[:4]]
        sentences = [f"A project I can speak to in detail is {project.get('name')}."]
        if project.get("description"):
            sentences.append(_as_sentence(str(project["description"])[:400]))
        if tech:
            sentences.append(f"It was built with {_join(tech)}.")
        sentences.append("I owned it end to end, from the initial design through release and the fixes that followed.")
        return " ".join(sentences)

    experience = [e for e in _as_list(candidate.get("experience")) if isinstance(e, dict)]
    if experience:
        entry = experience[0]
        role = entry.get("title") or "my current role"
        employer = entry.get("company")
        sentences = [f"The work I can describe best is from my time as {role}" + (f" at {employer}." if employer else ".")]
        if entry.get("description"):
            sentences.append(_as_sentence(str(entry["description"])[:400]))
        return " ".join(sentences)
    return ""


def _compose_strengths(job: dict[str, Any], candidate: dict[str, Any]) -> str:
    skills = _top_matching_skills(job, candidate, limit=3)
    years = candidate.get("years_of_experience")
    headline = candidate.get("headline") or candidate.get("current_designation")
    if not any([skills, years, headline]):
        return ""
    sentences = []
    if skills:
        sentences.append(f"My strongest areas are {_join(skills)}.")
    if headline and years:
        sentences.append(f"As a {headline} with {_format_number(years)} years of experience, I am used to owning a feature from design to production support.")
    elif headline:
        sentences.append(f"As a {headline}, I am used to owning a feature from design to production support.")
    sentences.append("I work well with reviewers and I would rather ask an early question than ship a wrong assumption.")
    return " ".join(sentences)


def _compose_motivation(job: dict[str, Any], candidate: dict[str, Any]) -> str:
    company = job.get("company_name") or "your team"
    title = job.get("title") or "this role"
    skills = _top_matching_skills(job, candidate, limit=3)
    sentences = [f"What motivates me is shipping software people actually use, which is why the {title} opening at {company} stands out."]
    if skills:
        sentences.append(f"I want to keep going deeper on {_join(skills)} rather than spreading myself thin.")
    sentences.append("Working with engineers who review carefully and explain their reasoning is what makes me improve fastest.")
    return " ".join(sentences)


def _company_hint(sender: str, subject: str) -> str | None:
    domain_match = re.search(r"@([A-Za-z0-9.\-]+)", sender or "")
    if domain_match:
        domain = domain_match.group(1).lower().strip(".")
        if domain not in _GENERIC_EMAIL_DOMAINS:
            parts = [p for p in domain.split(".") if p not in {"www", "mail", "careers", "jobs", "notifications", "no-reply", "noreply"}]
            if parts:
                root = parts[0]
                if root in {"co", "com"} and len(parts) > 1:
                    root = parts[1]
                if len(root) > 1:
                    return root.replace("-", " ").title()
    for regex in _COMPANY_HINT_RES:
        match = regex.search(subject or "")
        if match:
            hint = match.group("company").strip(" -–—|,.")
            if len(hint) > 1:
                return hint
    return None


def _job_title_hint(subject: str) -> str | None:
    for regex in _TITLE_HINT_RES:
        match = regex.search(subject or "")
        if match:
            hint = re.sub(r"\s+", " ", match.group("title")).strip(" -–—|,.")
            if 2 < len(hint) <= 60:
                return hint
    return None


__all__ = ["MockLLMProvider", "TASK_NAMES"]
