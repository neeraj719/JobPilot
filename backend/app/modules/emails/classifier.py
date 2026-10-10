"""Rule-first email classification (contract §13).

Cheap, deterministic keyword rules run first — they cost nothing, work offline and
cover the overwhelming majority of recruiting mail. Only when the rules are unsure
(confidence < :data:`AI_CONFIDENCE_THRESHOLD`) is ``ai.tasks.classify_email`` asked
for a second opinion, and its answer is used only when it is *more* confident.

The result records which engine decided (``RULES`` / ``AI``), the confidence and a
human-readable reason, so the UI can explain every automatic status change.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.models.enums import EmailClassification

logger = logging.getLogger(__name__)

#: Below this confidence the rules ask the LLM for a second opinion.
AI_CONFIDENCE_THRESHOLD = 0.6

CLASSIFIED_BY_RULES = "RULES"
CLASSIFIED_BY_AI = "AI"
CLASSIFIED_BY_USER = "USER"

# --------------------------------------------------------------------------- keyword rules
# (classification, weight, keywords). A hit in the subject counts double, a hit in the
# sender or body counts once. Rules are ordered by specificity: the earlier rule wins a
# tie, so "unfortunately ... thank you for applying" is a REJECTION, not a confirmation.

RULES: tuple[tuple[EmailClassification, int, tuple[str, ...]], ...] = (
    (
        EmailClassification.OFFER,
        3,
        (
            "offer letter",
            "pleased to offer",
            "happy to offer",
            "delighted to offer",
            "excited to offer",
            "job offer",
            "offer of employment",
            "we would like to extend an offer",
            "compensation package",
            "your offer",
        ),
    ),
    (
        EmailClassification.REJECTION,
        3,
        (
            "unfortunately",
            "we regret",
            "regret to inform",
            "not moving forward",
            "not move forward",
            "not to move forward",
            "will not be moving forward",
            "other candidates",
            "another candidate",
            "not selected",
            "was not successful",
            "no longer under consideration",
            "decided not to proceed",
            "pursue other candidates",
            "keep your profile on file",
        ),
    ),
    (
        EmailClassification.ASSESSMENT,
        3,
        (
            "coding challenge",
            "coding test",
            "online assessment",
            "assessment",
            "take-home",
            "take home assignment",
            "hackerrank",
            "codility",
            "codesignal",
            "hackerearth",
            "online test",
            "test link",
            "aptitude test",
            "complete the challenge",
            "programming test",
        ),
    ),
    (
        EmailClassification.INTERVIEW,
        3,
        (
            "interview",
            "schedule a call",
            "scheduling a call",
            "book a slot",
            "calendar invite",
            "technical round",
            "next round",
            "meet the team",
            "hiring manager call",
            "phone screen",
            "availability for a call",
            "invite you to speak",
            "set up a time",
        ),
    ),
    (
        EmailClassification.RECRUITER_MESSAGE,
        2,
        (
            "recruiter",
            "talent acquisition",
            "reaching out",
            "reached out",
            "reach out",
            "came across your",
            "your profile",
            "exciting opportunity",
            "opportunity",
            "hiring for",
            "we are hiring",
            "open role",
            "would you be interested",
        ),
    ),
    (
        EmailClassification.APPLICATION_RECEIVED,
        2,
        (
            "thank you for applying",
            "thanks for applying",
            "application received",
            "we received your application",
            "we have received your application",
            "your application has been received",
            "application submitted",
            "successfully applied",
            "application confirmation",
        ),
    ),
)

#: Phrases that, from a no-reply address, are an application confirmation.
CONFIRMATION_PHRASES: tuple[str, ...] = (
    "thank you for applying",
    "thanks for applying",
    "we received your application",
    "we have received your application",
    "your application has been received",
    "application received",
)

#: ATS / job-board senders: mail from here is job related even when the wording is bland.
JOB_BOARD_DOMAINS: frozenset[str] = frozenset(
    {
        "greenhouse.io",
        "greenhouse-mail.io",
        "us.greenhouse-mail.io",
        "lever.co",
        "hire.lever.co",
        "myworkday.com",
        "myworkdayjobs.com",
        "workday.com",
        "workdaymail.com",
        "smartrecruiters.com",
        "ashbyhq.com",
        "icims.com",
        "taleo.net",
        "successfactors.com",
        "jobvite.com",
        "naukri.com",
        "linkedin.com",
        "indeed.com",
        "indeedemail.com",
        "glassdoor.com",
        "foundit.in",
        "hirist.com",
        "wellfound.com",
        "angel.co",
        "internshala.com",
        "monster.com",
        "shine.com",
        "instahyre.com",
        "cutshort.io",
    }
)

#: Local parts used by automated senders.
NOREPLY_LOCAL_PARTS: tuple[str, ...] = ("noreply", "no-reply", "no_reply", "donotreply", "do-not-reply", "notifications", "notification")

_ADDRESS_RE = re.compile(r"<([^<>@\s]+@[^<>\s]+)>")
_BARE_ADDRESS_RE = re.compile(r"([^<>@\s,;]+@[^<>\s,;]+)")


# --------------------------------------------------------------------------- address helpers


def extract_address(sender: str | None) -> str:
    """The bare ``local@domain`` part of an RFC-5322 ``From`` header."""
    text = (sender or "").strip()
    if not text:
        return ""
    match = _ADDRESS_RE.search(text) or _BARE_ADDRESS_RE.search(text)
    return match.group(1).strip().strip("'\"").lower() if match else ""


def extract_domain(sender: str | None) -> str | None:
    """Lowercase domain of the sender address, or ``None`` when there is none."""
    address = extract_address(sender)
    if "@" not in address:
        return None
    domain = address.rsplit("@", 1)[1].strip(" .>").lower()
    return domain or None


def extract_display_name(sender: str | None) -> str:
    """The human-readable part of a ``From`` header (``"Acme Cloud" <a@b.com>`` → ``Acme Cloud``)."""
    text = (sender or "").strip()
    if not text:
        return ""
    if "<" in text:
        return text.split("<", 1)[0].strip().strip("'\"")
    if "@" in text:
        return ""
    return text.strip("'\"")


def is_job_board_domain(domain: str | None) -> bool:
    """True for ATS / job-board senders (``greenhouse-mail.io``, ``linkedin.com``...)."""
    if not domain:
        return False
    domain = domain.lower()
    return any(domain == known or domain.endswith(f".{known}") for known in JOB_BOARD_DOMAINS)


def is_noreply_sender(sender: str | None) -> bool:
    address = extract_address(sender)
    local = address.split("@", 1)[0] if "@" in address else address
    return any(part in local for part in NOREPLY_LOCAL_PARTS)


# --------------------------------------------------------------------------- result


@dataclass(frozen=True)
class ClassificationOutcome:
    """What the classifier decided, and why."""

    classification: EmailClassification
    confidence: float
    reason: str
    classified_by: str = CLASSIFIED_BY_RULES

    @property
    def is_confident(self) -> bool:
        return self.confidence >= AI_CONFIDENCE_THRESHOLD


# --------------------------------------------------------------------------- rules engine


def _confidence_for(score: int, runner_up: int) -> float:
    """Map a keyword score to a confidence, penalising an ambiguous runner-up."""
    confidence = min(0.95, 0.45 + 0.06 * score)
    if runner_up:
        confidence -= min(0.18, 0.05 * runner_up)
    return round(max(0.1, confidence), 2)


def classify_with_rules(subject: str | None, sender: str | None, body: str | None) -> ClassificationOutcome:
    """Deterministic keyword + sender classification. Never calls out to a model."""
    subject_l = (subject or "").lower()
    sender_l = (sender or "").lower()
    body_l = (body or "").lower()
    domain = extract_domain(sender)

    scores: dict[EmailClassification, int] = {}
    hits: dict[EmailClassification, list[str]] = {}
    for classification, weight, keywords in RULES:
        for keyword in keywords:
            score = 0
            if keyword in subject_l:
                score += 2 * weight
            if keyword in sender_l:
                score += weight
            if keyword in body_l:
                score += weight
            if score:
                scores[classification] = scores.get(classification, 0) + score
                hits.setdefault(classification, []).append(keyword)

    notes: list[str] = []

    # Sender heuristic 1: an automated "thank you for applying" is a confirmation.
    if is_noreply_sender(sender) and any(phrase in subject_l or phrase in body_l for phrase in CONFIRMATION_PHRASES):
        scores[EmailClassification.APPLICATION_RECEIVED] = scores.get(EmailClassification.APPLICATION_RECEIVED, 0) + 4
        notes.append("automated sender confirming an application")

    # Sender heuristic 2: ATS / job boards are always job related.
    job_board = is_job_board_domain(domain)
    if job_board:
        notes.append(f"sender domain {domain} is a known ATS/job board")
        for classification in list(scores):
            scores[classification] += 1

    if not scores:
        reason = "No recruiting keywords matched the subject, sender or body."
        if notes:
            reason = f"{reason} Noted: {'; '.join(notes)}."
        # A job-board sender with no keywords is suspicious enough to ask the model.
        return ClassificationOutcome(EmailClassification.OTHER, 0.25 if job_board else 0.3, reason)

    order = [rule[0] for rule in RULES]
    ranked = sorted(scores.items(), key=lambda item: (-item[1], order.index(item[0])))
    classification, score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0
    matched = ", ".join(sorted(set(hits.get(classification, [])))[:3])
    reason = f"Matched {classification.value.replace('_', ' ').lower()} keywords: {matched}." if matched else "Matched sender heuristics."
    if notes:
        reason = f"{reason} Noted: {'; '.join(notes)}."
    return ClassificationOutcome(classification, _confidence_for(score, runner_up), reason)


# --------------------------------------------------------------------------- public API


def classify(subject: str | None, sender: str | None, body: str | None, *, use_ai: bool = True) -> ClassificationOutcome:
    """Classify one email: rules first, LLM only as a tie-breaker.

    The AI answer is adopted only when it is strictly more confident than the rules,
    so a deterministic, explainable result always wins a draw.
    """
    outcome = classify_with_rules(subject, sender, body)
    if outcome.is_confident or not use_ai:
        return outcome

    try:
        from app.modules.ai.tasks import classify_email as ai_classify_email  # noqa: PLC0415 - optional, lazy

        ai_result = ai_classify_email(subject or "", sender or "", body or "")
    except Exception as exc:  # noqa: BLE001 - the rules result is always a valid answer
        logger.warning("AI email classification unavailable (%s); keeping the rule-based result", exc)
        return outcome

    ai_confidence = round(float(ai_result.confidence or 0.0), 2)
    if ai_confidence <= outcome.confidence:
        logger.debug("Keeping rule classification %s (%.2f >= AI %.2f)", outcome.classification, outcome.confidence, ai_confidence)
        return outcome
    reason = ai_result.reason or f"Model classified this as {ai_result.classification.value}."
    return ClassificationOutcome(
        classification=ai_result.classification,
        confidence=ai_confidence,
        reason=f"{reason} (rules were unsure: {outcome.reason})",
        classified_by=CLASSIFIED_BY_AI,
    )


__all__ = [
    "AI_CONFIDENCE_THRESHOLD",
    "CLASSIFIED_BY_AI",
    "CLASSIFIED_BY_RULES",
    "CLASSIFIED_BY_USER",
    "ClassificationOutcome",
    "JOB_BOARD_DOMAINS",
    "classify",
    "classify_with_rules",
    "extract_address",
    "extract_display_name",
    "extract_domain",
    "is_job_board_domain",
    "is_noreply_sender",
]
