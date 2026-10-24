"""LinkedIn connection service: status, sync, diff against the master profile, apply,
export linking, resume creation and the scheduled check.

The rule that shapes everything here: **LinkedIn data never reaches the profile or a resume
without the user's say-so.** ``sync`` only stores what LinkedIn returned (normalised, on the
connection row) and computes a diff; ``apply`` writes exactly the rows the user ticked; the
scheduler syncs and *notifies*, it never applies. Lists are only ever added to or updated in
place by stable keys — nothing on the profile is removed because LinkedIn does not show it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.actor import actor_context
from app.core.audit import audit
from app.core.config import settings
from app.core.database import soft_delete
from app.core.exceptions import AppError, ExternalServiceError, ValidationFailed
from app.models.base import utcnow
from app.models.enums import Actor, NotificationType, ResumeChangeSource, ResumeKind
from app.models.linkedin import (
    LINKEDIN_CONNECTED,
    LINKEDIN_PENDING,
    SNAPSHOT_DMA,
    SNAPSHOT_EXPORT,
    SNAPSHOT_OIDC,
    LinkedInConnection,
)
from app.models.profile import UserProfile
from app.models.resume import Resume
from app.modules.ai.schemas import ParsedResume
from app.modules.integrations import linkedin_oauth as oauth
from app.modules.integrations.linkedin_schemas import (
    LinkedInApplyResult,
    LinkedInDiff,
    LinkedInDiffRow,
    LinkedInDiffSummary,
    LinkedInHistoryCounts,
    LinkedInStatus,
    LinkedInSyncResult,
)

logger = logging.getLogger(__name__)

#: Where the scheduled check's notification sends the user.
REVIEW_LINK = "/resume/new?source=linkedin&review=1"
MAX_KEY_CHARS = 300

#: Member Snapshot API domain → the export CSV it mirrors (same field names).
DOMAIN_FILES = {
    "PROFILE": "profile.csv",
    "POSITIONS": "positions.csv",
    "EDUCATION": "education.csv",
    "SKILLS": "skills.csv",
    "CERTIFICATIONS": "certifications.csv",
    "LANGUAGES": "languages.csv",
}

SCALAR_FIELDS: tuple[tuple[str, str], ...] = (
    ("full_name", "Full name"),
    ("first_name", "First name"),
    ("last_name", "Last name"),
    ("email", "Email"),
    ("headline", "Headline"),
    ("summary", "Summary"),
    ("current_designation", "Current title"),
    ("current_company", "Current company"),
    ("linkedin_url", "LinkedIn URL"),
)
LIST_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("previous_companies", "Experience", "experience"),
    ("education", "Education", "education"),
    ("skills", "Skill", "skills"),
    ("certifications", "Certification", "certifications"),
    ("languages", "Language", "languages"),
)
_SCALAR_LIMITS = {"full_name": 255, "first_name": 120, "last_name": 120, "email": 255, "headline": 255,
                  "current_designation": 255, "current_company": 255, "linkedin_url": 500}

NOTE_BASICS_ONLY = (
    "LinkedIn shared your name, email and photo only — its standard sign-in does not include positions, "
    "education or skills. Add your LinkedIn export for the full history."
)


# --------------------------------------------------------------------------- small helpers


def _s(value: Any) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None


def _norm(value: Any) -> str:
    return (_s(value) or "").casefold()


def _clean(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if v not in (None, "", [], {})}


def _has_history(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    return any(data.get(key) for key in ("experience", "education", "skills", "certifications", "languages"))


def history_of(snapshot: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """The richest data on the connection: the live DMA snapshot first, then the export."""
    if _has_history(snapshot.get("dma")):
        return snapshot["dma"], SNAPSHOT_DMA
    if _has_history(snapshot.get("export")):
        return snapshot["export"], SNAPSHOT_EXPORT
    return None, None


def snapshot_source_of(snapshot: dict[str, Any]) -> str:
    return history_of(snapshot)[1] or SNAPSHOT_OIDC


def history_counts(history: dict[str, Any] | None) -> LinkedInHistoryCounts:
    if not history:
        return LinkedInHistoryCounts()
    return LinkedInHistoryCounts(
        positions=len(history.get("experience") or []),
        education=len(history.get("education") or []),
        skills=len(history.get("skills") or []),
        certifications=len(history.get("certifications") or []),
        languages=len(history.get("languages") or []),
    )


def parse_snapshot_domains(domains: dict[str, list[dict[str, Any]]]) -> ParsedResume:
    """Member Snapshot API rows → ``ParsedResume`` with the export normaliser."""
    from app.modules.resumes.importers import parse_linkedin_rows

    rows = {DOMAIN_FILES[d]: list(items) for d, items in domains.items() if d in DOMAIN_FILES}
    return parse_linkedin_rows(rows)


def _split_name(name: str | None) -> tuple[str | None, str | None]:
    from app.modules.profiles.service import split_full_name

    return split_full_name(name)


# --------------------------------------------------------------------------- incoming facts


def incoming_facts(snapshot: dict[str, Any]) -> dict[str, Any]:
    """What LinkedIn says, in ``UserProfile`` terms: ``{scalars: {...}, lists: {...}}``."""
    identity = snapshot.get("identity") or {}
    history, _source = history_of(snapshot)
    history = history or {}

    scalars: dict[str, Any] = {}
    name = _s(identity.get("name")) or _s(history.get("name"))
    first, last = _s(identity.get("given_name")), _s(identity.get("family_name"))
    if name and not (first or last):
        first, last = _split_name(name)
    scalars["full_name"] = name
    scalars["first_name"] = first
    scalars["last_name"] = last
    email = _s(identity.get("email")) if identity.get("email_verified") is not False else None
    scalars["email"] = email or _s(history.get("email"))
    scalars["headline"] = _s(history.get("headline"))
    scalars["summary"] = (str(history.get("summary") or "").strip() or None)
    links = history.get("links") or {}
    scalars["linkedin_url"] = _s(links.get("linkedin")) if isinstance(links, dict) else None

    experience = [e for e in history.get("experience") or [] if isinstance(e, dict)]
    current = next((e for e in experience if _norm(e.get("end")) in ("", "present") and _s(e.get("start"))), None)
    if current:
        scalars["current_designation"] = _s(current.get("title"))
        scalars["current_company"] = _s(current.get("company"))
    for field, limit in _SCALAR_LIMITS.items():
        if scalars.get(field):
            scalars[field] = str(scalars[field])[:limit]

    lists: dict[str, list[Any]] = {
        "previous_companies": [
            _clean(
                {
                    "company": _s(e.get("company")),
                    "title": _s(e.get("title")),
                    "start": _s(e.get("start")),
                    "end": _s(e.get("end")),
                    "location": _s(e.get("location")),
                    "description": (str(e.get("description") or "").strip() or None),
                }
            )
            for e in experience
            if _s(e.get("company")) or _s(e.get("title"))
        ],
        "education": [
            _clean(
                {
                    "institution": _s(e.get("institution")),
                    "degree": _s(e.get("degree")),
                    "field": _s(e.get("field")),
                    "start": _s(e.get("start")),
                    "end": _s(e.get("end")),
                }
            )
            for e in history.get("education") or []
            if isinstance(e, dict) and (_s(e.get("institution")) or _s(e.get("degree")))
        ],
        "skills": [s for s in (_s(x) for x in history.get("skills") or []) if s],
        "certifications": [
            _clean({"name": _s(c.get("name")), "issuer": _s(c.get("issuer")), "year": _s(c.get("year"))})
            for c in history.get("certifications") or []
            if isinstance(c, dict) and _s(c.get("name"))
        ],
        "languages": [s for s in (_s(x) for x in history.get("languages") or []) if s],
    }
    return {"scalars": scalars, "lists": lists}


# --------------------------------------------------------------------------- diff


def _item_key(field: str, item: Any) -> str:
    if field == "previous_companies" and isinstance(item, dict):
        key = f"{_norm(item.get('company'))}|{_norm(item.get('title') or item.get('designation'))}"
    elif field == "education" and isinstance(item, dict):
        key = f"{_norm(item.get('institution') or item.get('school'))}|{_norm(item.get('degree'))}"
    elif field == "certifications" and isinstance(item, dict):
        key = _norm(item.get("name"))
    elif field == "languages":
        name = item if isinstance(item, str) else (item.get("name") if isinstance(item, dict) else "")
        key = _norm(str(name or "").split(" (")[0])
    else:  # skills
        key = _norm(item if isinstance(item, str) else (item.get("name") if isinstance(item, dict) else item))
    return key[:MAX_KEY_CHARS]


def _differs(current: dict[str, Any], incoming: dict[str, Any]) -> bool:
    """True when an incoming non-empty value disagrees with the profile's."""
    aliases = {"title": ("title", "designation"), "institution": ("institution", "school")}
    for key, value in incoming.items():
        if value in (None, ""):
            continue
        names = aliases.get(key, (key,))
        current_value = next((current.get(n) for n in names if current.get(n) not in (None, "")), None)
        if _norm(current_value) != _norm(value):
            return True
    return False


def compute_diff(snapshot: dict[str, Any], profile: UserProfile | None, *, history_source: str | None = None) -> LinkedInDiff:
    facts = incoming_facts(snapshot or {})
    rows: list[LinkedInDiffRow] = []

    for field, label in SCALAR_FIELDS:
        incoming = facts["scalars"].get(field)
        if not incoming:
            continue
        current = getattr(profile, field, None) if profile is not None else None
        current = current if _s(current) else None
        if current is None:
            action = "add"
        elif _norm(current) == _norm(incoming):
            action = "same"
        else:
            action = "replace"
        rows.append(
            LinkedInDiffRow(
                id=field, field=field, label=label, group="basics", current=current, incoming=incoming,
                action=action, default_selected=action == "add",
            )
        )

    for field, label, group in LIST_FIELDS:
        incoming_items = facts["lists"].get(field) or []
        if not incoming_items:
            continue
        current_items = list(getattr(profile, field, None) or []) if profile is not None else []
        if field == "skills" and profile is not None:
            current_items = current_items + list(profile.technologies or [])
        index: dict[str, Any] = {}
        for item in current_items:
            index.setdefault(_item_key(field, item), item)
        seen: dict[str, int] = {}
        for item in incoming_items:
            key = _item_key(field, item)
            if not key.strip("|"):
                continue
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 1:
                if field in ("skills", "languages", "certifications"):
                    continue  # the same skill twice is one skill
                key = f"{key}#{seen[key]}"
            current = index.get(key)
            if current is None:
                action = "add"
            elif isinstance(item, dict) and isinstance(current, dict) and _differs(current, item):
                action = "replace"
            else:
                action = "same"
            incoming_value: Any = item
            if action == "replace":
                incoming_value = {**current, **{k: v for k, v in item.items() if v not in (None, "")}}
            rows.append(
                LinkedInDiffRow(
                    id=f"{field}:{key}", field=field, label=label, group=group, key=key,
                    current=current, incoming=incoming_value, action=action, default_selected=action == "add",
                )
            )

    adds = sum(1 for r in rows if r.action == "add")
    replaces = sum(1 for r in rows if r.action == "replace")
    same = sum(1 for r in rows if r.action == "same")
    return LinkedInDiff(
        source=snapshot_source_of(snapshot or {}),
        history_source=history_source if history_source is not None else history_of(snapshot or {})[1],
        rows=rows, adds=adds, replaces=replaces, same=same, changes=adds + replaces,
    )


def diff_fingerprint(diff: LinkedInDiff) -> str:
    actionable = sorted(
        (r.id, json.dumps(r.incoming, sort_keys=True, default=str)) for r in diff.rows if r.action != "same"
    )
    return hashlib.sha256(json.dumps(actionable).encode("utf-8")).hexdigest()[:32]


def diff_summary(diff: LinkedInDiff, trigger: str, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = {
        "synced_at": utcnow().isoformat(),
        "source": diff.source,
        "adds": diff.adds,
        "replaces": diff.replaces,
        "same": diff.same,
        "changes": diff.changes,
        "trigger": trigger,
        "fingerprint": diff_fingerprint(diff),
    }
    if previous and previous.get("notified_fingerprint"):
        summary["notified_fingerprint"] = previous["notified_fingerprint"]
    return summary


# --------------------------------------------------------------------------- rows


def _profile(db: Session, user_id: uuid.UUID) -> UserProfile | None:
    return db.scalars(select(UserProfile).where(UserProfile.user_id == user_id)).first()


def _require_connection(db: Session, user_id: uuid.UUID) -> LinkedInConnection:
    connection = oauth.get_connection(db, user_id)
    if connection is None or connection.status == LINKEDIN_PENDING or not connection.subject:
        raise ValidationFailed("LinkedIn is not connected. Connect it first.", code="not_connected")
    return connection


def _export_age_days(connection: LinkedInConnection) -> int | None:
    if connection.export_imported_at is None:
        return None
    return max(0, (utcnow() - connection.export_imported_at).days)


def status_of(db: Session, user_id: uuid.UUID) -> LinkedInStatus:
    """Connection state for the UI. Never includes a token, the state or the verifier."""
    base = LinkedInStatus(
        configured=oauth.is_configured(),
        dma_enabled=settings.LINKEDIN_DMA_ENABLED,
        auto_sync_hours=settings.LINKEDIN_AUTO_SYNC_HOURS,
        export_stale_days=settings.LINKEDIN_EXPORT_STALE_DAYS,
    )
    connection = oauth.get_connection(db, user_id)
    if connection is None or (connection.status == LINKEDIN_PENDING and not connection.subject):
        if connection is not None:
            base.status = "pending"
        return base
    snapshot = connection.profile_snapshot or {}
    history, history_source = history_of(snapshot)
    scopes = [str(s) for s in (connection.scopes or [])]
    age = _export_age_days(connection)
    summary = connection.last_sync_diff or {}
    profile = _profile(db, user_id)
    pending = compute_diff(snapshot, profile).changes if snapshot.get("identity") else 0
    return base.model_copy(
        update={
            "status": connection.status,
            "connected": connection.status == LINKEDIN_CONNECTED,
            "name": connection.name,
            "email": connection.email,
            "picture_url": connection.picture_url,
            "locale": connection.locale,
            "scopes": scopes,
            "dma_granted": oauth.DMA_SCOPE in scopes,
            "dma_error": snapshot.get("dma_error"),
            "connected_at": connection.connected_at,
            "token_expires_at": connection.token_expires_at,
            "last_synced_at": connection.last_synced_at,
            "auto_sync": connection.auto_sync,
            "snapshot_source": connection.snapshot_source,
            "history_source": history_source,
            "history_counts": history_counts(history),
            "export_imported_at": connection.export_imported_at,
            "export_stale": age is not None and age > settings.LINKEDIN_EXPORT_STALE_DAYS,
            "last_error": connection.last_error,
            "pending_changes": pending,
            "last_sync_diff": LinkedInDiffSummary.model_validate(summary) if summary else None,
        }
    )


def _notes(connection: LinkedInConnection, diff: LinkedInDiff) -> list[str]:
    notes: list[str] = []
    snapshot = connection.profile_snapshot or {}
    if snapshot.get("dma_error") and diff.history_source != SNAPSHOT_DMA:
        notes.append(str(snapshot["dma_error"]))  # already says what is missing and what to do
    elif diff.history_source is None:
        notes.append(NOTE_BASICS_ONLY)
    age = _export_age_days(connection)
    if age is not None and age > settings.LINKEDIN_EXPORT_STALE_DAYS and diff.history_source == SNAPSHOT_EXPORT:
        notes.append(f"Your LinkedIn export is {age} days old. Download a fresh copy to pick up recent changes.")
    return notes


def current_diff(db: Session, user_id: uuid.UUID) -> LinkedInSyncResult:
    connection = _require_connection(db, user_id)
    diff = compute_diff(connection.profile_snapshot or {}, _profile(db, user_id))
    return LinkedInSyncResult(status=status_of(db, user_id), diff=diff, notes=_notes(connection, diff))


# --------------------------------------------------------------------------- sync


def sync(db: Session, user_id: uuid.UUID, *, trigger: str = "manual") -> LinkedInSyncResult:
    """Re-read LinkedIn (userinfo, plus the snapshot domains when DMA was granted), store the
    normalised snapshot and return the diff against the profile. Writes nothing to the profile."""
    oauth.ensure_configured()
    connection = _require_connection(db, user_id)
    token = oauth.access_token_for(db, connection)
    try:
        info = oauth.fetch_userinfo(token)
    except oauth.TokenRejected:
        if oauth.token_is_expired(connection):
            oauth.mark_expired(db, connection)
        else:
            oauth.mark_revoked(db, connection)
        raise ValidationFailed("LinkedIn no longer accepts this connection. Reconnect LinkedIn.", code="reconnect_required") from None
    except ExternalServiceError as exc:
        connection.last_error = exc.message[: oauth.MAX_ERROR_CHARS]
        db.flush()
        raise
    identity = oauth.normalise_identity(info)
    oauth.apply_identity(connection, identity)
    snapshot = dict(connection.profile_snapshot or {})
    snapshot["identity"] = identity

    dma_error: str | None = None
    scopes = [str(s) for s in (connection.scopes or [])]
    if settings.LINKEDIN_DMA_ENABLED and oauth.DMA_SCOPE in scopes:
        try:
            domains = oauth.fetch_snapshot(token)
            snapshot["dma"] = parse_snapshot_domains(domains).model_dump(mode="json")
            snapshot["dma_fetched_at"] = utcnow().isoformat()
        except oauth.DmaUnavailable:
            dma_error = (
                "LinkedIn did not share your full profile (Member Data Portability is available to EU/EEA members "
                "once LinkedIn approves the app). Add your LinkedIn export instead."
            )
        except oauth.TokenRejected:
            oauth.mark_revoked(db, connection)
            raise ValidationFailed("LinkedIn no longer accepts this connection. Reconnect LinkedIn.", code="reconnect_required") from None
        except ExternalServiceError as exc:
            dma_error = f"{exc.message} Your basics were still updated."
    elif settings.LINKEDIN_DMA_ENABLED:
        dma_error = (
            "LinkedIn did not grant access to your full profile (Member Data Portability), so only your basics "
            "were updated. Add your LinkedIn export for positions, education and skills."
        )
    snapshot["dma_error"] = dma_error
    snapshot["fetched_at"] = utcnow().isoformat()
    connection.profile_snapshot = snapshot
    connection.snapshot_source = snapshot_source_of(snapshot)
    connection.last_synced_at = utcnow()
    connection.status = LINKEDIN_CONNECTED
    connection.last_error = None

    diff = compute_diff(snapshot, _profile(db, user_id))
    connection.last_sync_diff = diff_summary(diff, trigger, connection.last_sync_diff)
    db.flush()
    audit(
        db,
        action="integration.linkedin.synced",
        message=f"LinkedIn sync ({trigger}): {diff.changes} change(s) to review",
        user_id=user_id,
        actor=Actor.SYSTEM if trigger == "scheduled" else Actor.USER,
        meta={"trigger": trigger, "source": diff.source, "adds": diff.adds, "replaces": diff.replaces, "same": diff.same},
    )
    return LinkedInSyncResult(status=status_of(db, user_id), diff=diff, notes=_notes(connection, diff))


# --------------------------------------------------------------------------- apply


def apply_changes(db: Session, user_id: uuid.UUID, change_ids: list[str]) -> LinkedInApplyResult:
    """Write exactly the ticked rows to the master profile (recomputed server side: the client
    only names rows, it never supplies values)."""
    from app.modules.profiles.service import get_or_create_profile

    connection = _require_connection(db, user_id)
    profile = get_or_create_profile(db, user_id)
    diff = compute_diff(connection.profile_snapshot or {}, profile)
    wanted = {str(c) for c in change_ids}
    applied_rows: list[LinkedInDiffRow] = []
    for row in diff.rows:
        if row.id not in wanted or row.action == "same":
            continue
        if row.group == "basics":
            setattr(profile, row.field, row.incoming)
        else:
            items = list(getattr(profile, row.field) or [])
            if row.action == "add":
                items.append(row.incoming)
            else:
                position = next((i for i, item in enumerate(items) if _item_key(row.field, item) == (row.key or "").split("#")[0]), None)
                if position is None:
                    items.append(row.incoming)
                else:
                    items[position] = row.incoming
            setattr(profile, row.field, items)
        applied_rows.append(row)

    applied_ids = {r.id for r in applied_rows}
    if "full_name" in applied_ids and profile.full_name:
        first, last = _split_name(profile.full_name)
        profile.first_name = profile.first_name or first
        profile.last_name = profile.last_name or last
    db.flush()

    fields = sorted({r.field for r in applied_rows})
    if applied_rows:
        audit(
            db,
            action="integration.linkedin.profile_applied",
            message=f"Applied {len(applied_rows)} LinkedIn change(s) to the profile",
            user_id=user_id,
            actor=Actor.USER,
            # Field names and counts only — never the values (names, emails…).
            meta={
                "fields": fields,
                "applied": len(applied_rows),
                "adds": sum(1 for r in applied_rows if r.action == "add"),
                "replaces": sum(1 for r in applied_rows if r.action == "replace"),
                "source": diff.source,
            },
        )
    remaining = compute_diff(connection.profile_snapshot or {}, profile)
    connection.last_sync_diff = {**diff_summary(remaining, "apply", connection.last_sync_diff),
                                 "synced_at": (connection.last_sync_diff or {}).get("synced_at") or utcnow().isoformat()}
    db.flush()
    return LinkedInApplyResult(
        applied=len(applied_rows),
        fields=fields,
        skipped=sorted(wanted - applied_ids),
        status=status_of(db, user_id),
        diff=remaining,
    )


# --------------------------------------------------------------------------- settings / export / disconnect


def set_auto_sync(db: Session, user_id: uuid.UUID, auto_sync: bool) -> LinkedInStatus:
    connection = _require_connection(db, user_id)
    connection.auto_sync = bool(auto_sync)
    db.flush()
    audit(
        db,
        action="integration.linkedin.auto_sync_changed",
        message=f"LinkedIn auto-sync {'on' if auto_sync else 'off'}",
        user_id=user_id,
        actor=Actor.USER,
        meta={"auto_sync": bool(auto_sync)},
    )
    return status_of(db, user_id)


def record_export(db: Session, user_id: uuid.UUID, parsed: ParsedResume) -> bool:
    """Link a LinkedIn export to the connection (no-op when LinkedIn is not connected)."""
    connection = oauth.get_connection(db, user_id)
    if connection is None or connection.status == LINKEDIN_PENDING or not connection.subject:
        return False
    snapshot = dict(connection.profile_snapshot or {})
    snapshot["export"] = parsed.model_dump(mode="json")
    connection.profile_snapshot = snapshot
    connection.export_imported_at = utcnow()
    connection.snapshot_source = snapshot_source_of(snapshot)
    db.flush()
    logger.info("LinkedIn export linked to the connection of user %s", user_id)
    return True


def import_export(db: Session, user_id: uuid.UUID, files: list[tuple[str, bytes]]) -> LinkedInSyncResult:
    """"Add export for full history": read the ZIP in memory, keep only the normalised details
    on the connection, and return the diff (nothing is written to the profile)."""
    from app.modules.resumes import importers

    connection = _require_connection(db, user_id)
    members = importers.linkedin_members(files)
    if not ({"profile.csv", "positions.csv"} & set(members)):
        raise ValidationFailed(
            "No LinkedIn profile data found. Upload the ZIP from LinkedIn's “Get a copy of your data”, "
            "or at least Profile.csv and Positions.csv.",
            code="linkedin_data_missing",
            details={"found": sorted(members)},
        )
    record_export(db, user_id, importers.parse_linkedin(members))
    diff = compute_diff(connection.profile_snapshot or {}, _profile(db, user_id))
    connection.last_sync_diff = diff_summary(diff, "export", connection.last_sync_diff)
    db.flush()
    audit(
        db,
        action="integration.linkedin.export_linked",
        message="LinkedIn export added to the connection",
        user_id=user_id,
        actor=Actor.USER,
        meta={"files": sorted(members), "changes": diff.changes},
    )
    return LinkedInSyncResult(status=status_of(db, user_id), diff=diff, notes=_notes(connection, diff))


def disconnect(db: Session, user_id: uuid.UUID) -> LinkedInStatus:
    """Revoke at LinkedIn (best effort), wipe tokens and the stored snapshot, soft delete."""
    connection = oauth.get_connection(db, user_id)
    if connection is None:
        return status_of(db, user_id)
    revoked = False
    try:
        revoked = oauth.revoke_token(oauth._decrypt(connection.encrypted_access_token))
    except ExternalServiceError:
        logger.warning("Stored LinkedIn token for user %s was unreadable; wiping it anyway", user_id)
    oauth.wipe_tokens(connection)
    connection.profile_snapshot = {}
    connection.last_sync_diff = {}
    connection.status = "revoked"
    soft_delete(connection)
    db.flush()
    audit(
        db,
        action="integration.linkedin.disconnected",
        message="LinkedIn disconnected; tokens and stored LinkedIn data wiped",
        user_id=user_id,
        actor=Actor.USER,
        meta={"revoked_at_linkedin": revoked},
    )
    return status_of(db, user_id)


# --------------------------------------------------------------------------- resume


def build_parsed_resume(db: Session, user_id: uuid.UUID) -> tuple[ParsedResume, str]:
    """``(ParsedResume, source)``: DMA / export history through the export normaliser, else the
    profile-based builder with LinkedIn's identity filling empty basics."""
    from app.modules.resumes.importers import prefill_from_profile

    connection = _require_connection(db, user_id)
    snapshot = connection.profile_snapshot or {}
    identity = snapshot.get("identity") or {}
    history, source = history_of(snapshot)
    parsed = ParsedResume.model_validate(history) if history else prefill_from_profile(db, user_id)
    updates: dict[str, Any] = {}
    if not parsed.name and identity.get("name"):
        updates["name"] = identity["name"]
    if not parsed.email and identity.get("email") and identity.get("email_verified") is not False:
        updates["email"] = identity["email"]
    if history:
        # Contact details the user keeps on the profile (phone, links) are theirs too.
        profile = _profile(db, user_id)
        if profile is not None and not parsed.phone and _s(profile.phone):
            updates["phone"] = _s(profile.phone)
    if updates:
        parsed = parsed.model_copy(update=updates)
    return parsed, source or SNAPSHOT_OIDC


def create_resume(
    db: Session,
    user_id: uuid.UUID,
    *,
    name: str | None = None,
    target_role: str | None = None,
    template: str | None = None,
    set_default: bool = False,
) -> Resume:
    from app.modules.resumes import service as resume_service
    from app.modules.resumes.importers import default_target_role

    parsed, source = build_parsed_resume(db, user_id)
    if not (parsed.name or parsed.experience or parsed.education or parsed.skills):
        raise ValidationFailed("There is nothing to build a resume from yet. Sync LinkedIn or fill in your profile.", code="nothing_to_import")
    display = _s(name) or (f"{parsed.name} - LinkedIn" if parsed.name else "LinkedIn resume")
    resume = resume_service.create_resume_from_parsed(
        db,
        user_id,
        parsed,
        name=display,
        kind=ResumeKind.CREATED,
        target_role=target_role or default_target_role(db, user_id),
        template=template or "classic",
        set_default=set_default,
        note="Imported from LinkedIn",
        change_source=ResumeChangeSource.SYSTEM,
    )
    audit(
        db,
        action="integration.linkedin.resume_created",
        message="Resume created from LinkedIn",
        user_id=user_id,
        actor=Actor.USER,
        meta={"source": source, "resume_id": str(resume.id), "positions": len(parsed.experience)},
    )
    return resume


# --------------------------------------------------------------------------- scheduled check


def _notify_changes(db: Session, connection: LinkedInConnection, result: LinkedInSyncResult) -> bool:
    from app.modules.notifications.service import notify

    diff = result.diff
    summary = dict(connection.last_sync_diff or {})
    fingerprint = summary.get("fingerprint")
    if diff.changes <= 0 or not fingerprint or summary.get("notified_fingerprint") == fingerprint:
        return False
    plural = "" if diff.changes == 1 else "s"
    notify(
        db,
        connection.user_id,
        NotificationType.SYSTEM,
        f"LinkedIn: {diff.changes} change{plural} found — review",
        body="Your LinkedIn details differ from your profile. Nothing was changed: review and choose what to apply.",
        link=REVIEW_LINK,
        meta={"kind": "linkedin_sync", "changes": diff.changes, "adds": diff.adds, "replaces": diff.replaces},
    )
    summary["notified_fingerprint"] = fingerprint
    connection.last_sync_diff = summary
    db.flush()
    return True


def due_connections(db: Session, now=None) -> list[LinkedInConnection]:  # noqa: ANN001
    now = now or utcnow()
    # Five minutes of slack so an interval tick that lands just early still counts.
    cutoff = now - timedelta(hours=settings.LINKEDIN_AUTO_SYNC_HOURS) + timedelta(minutes=5)
    return list(
        db.scalars(
            select(LinkedInConnection).where(
                LinkedInConnection.auto_sync.is_(True),
                LinkedInConnection.status == LINKEDIN_CONNECTED,
                LinkedInConnection.encrypted_access_token.is_not(None),
                or_(LinkedInConnection.last_synced_at.is_(None), LinkedInConnection.last_synced_at <= cutoff),
            )
        )
    )


def sync_due_connections(db: Session, now=None) -> dict[str, str]:  # noqa: ANN001
    """The scheduler job: sync every due connection, notify about new changes. Never applies
    anything, never raises; users without the Resume Studio module are skipped."""
    from app.modules.workspace.service import module_available

    if not oauth.is_configured():
        return {}
    results: dict[str, str] = {}
    for connection in due_connections(db, now):
        user_id = connection.user_id
        if not module_available(db, user_id, "resume"):
            logger.info("Skipping LinkedIn auto-sync for user %s: the Resume Studio module is off", user_id)
            results[str(user_id)] = "skipped_module"
            continue
        try:
            with actor_context(user_id):
                result = sync(db, user_id, trigger="scheduled")
                notified = _notify_changes(db, connection, result)
            db.commit()
            results[str(user_id)] = f"synced:{result.diff.changes}" + (":notified" if notified else "")
        except AppError as exc:
            db.commit()  # keep the expired / revoked marker
            results[str(user_id)] = exc.code or "error"
        except Exception as exc:  # noqa: BLE001 - one broken connection must not stop the rest
            logger.warning("Scheduled LinkedIn sync failed for user %s: %s", user_id, type(exc).__name__)
            db.rollback()
            results[str(user_id)] = "error"
    if results:
        logger.info("Scheduled LinkedIn sync: %s", results)
    return results


__all__ = [
    "apply_changes",
    "build_parsed_resume",
    "compute_diff",
    "create_resume",
    "current_diff",
    "disconnect",
    "due_connections",
    "history_of",
    "import_export",
    "incoming_facts",
    "parse_snapshot_domains",
    "record_export",
    "set_auto_sync",
    "status_of",
    "sync",
    "sync_due_connections",
]
