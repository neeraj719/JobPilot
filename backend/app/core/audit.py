"""Audit logging helper used by every module (spec §27).

Usage::

    from app.core.audit import audit
    audit(db, action="job.found", message="Google — Software Engineer", user_id=user.id, actor=Actor.AUTOMATION)

The helper only ``db.add``s — the caller controls the transaction.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.base import utcnow
from app.models.enums import Actor, AuditLevel

logger = logging.getLogger("audit")


def audit(
    db: Session,
    *,
    action: str,
    message: str,
    user_id: uuid.UUID | None = None,
    application_id: uuid.UUID | None = None,
    automation_run_id: uuid.UUID | None = None,
    actor: Actor = Actor.SYSTEM,
    level: AuditLevel = AuditLevel.INFO,
    meta: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        application_id=application_id,
        automation_run_id=automation_run_id,
        actor=actor,
        level=level,
        action=action,
        message=message,
        meta=meta or {},
        ip_address=ip_address,
        created_at=utcnow(),
    )
    db.add(entry)
    log_fn = {AuditLevel.INFO: logger.info, AuditLevel.WARN: logger.warning, AuditLevel.ERROR: logger.error}[level]
    log_fn("%s | %s", action, message, extra={"user_id": str(user_id) if user_id else None, "application_id": str(application_id) if application_id else None})
    return entry


def list_audit_logs(
    db: Session,
    *,
    user_id: uuid.UUID,
    application_id: uuid.UUID | None = None,
    automation_run_id: uuid.UUID | None = None,
    action_prefix: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.user_id == user_id)
    if application_id:
        stmt = stmt.where(AuditLog.application_id == application_id)
    if automation_run_id:
        stmt = stmt.where(AuditLog.automation_run_id == automation_run_id)
    if action_prefix:
        stmt = stmt.where(AuditLog.action.like(f"{action_prefix}%"))
    stmt = stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    return list(db.scalars(stmt))
