"""Email schemas (contract §13).

``IncomingEmail`` is the provider-agnostic envelope every ingestion path funnels
through: the Gmail client builds one per fetched message, the demo ATS builds one
for its simulated confirmation, and ``POST /emails/simulate`` builds one from the
requested classification.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.base import utcnow
from app.models.enums import EmailClassification

#: ``body_text`` is truncated to this many characters in list responses (contract §13).
LIST_BODY_LIMIT = 2000


class IncomingEmail(BaseModel):
    """One message handed to :func:`app.modules.emails.service.ingest_message`."""

    model_config = ConfigDict(from_attributes=True)

    provider_message_id: str = Field(min_length=1, max_length=255)
    thread_id: str | None = Field(default=None, max_length=255)
    sender: str = Field(default="", max_length=500)
    recipient: str | None = Field(default=None, max_length=500)
    subject: str = Field(default="", max_length=1000)
    snippet: str | None = None
    body_text: str | None = None
    received_at: datetime = Field(default_factory=utcnow)
    raw_headers: dict[str, Any] = Field(default_factory=dict)
    is_simulated: bool = False

    @property
    def text(self) -> str:
        """Body text with the snippet as a fallback (never ``None``)."""
        return self.body_text or self.snippet or ""


class EmailMessageRead(BaseModel):
    """API representation of a stored message. Never carries credentials."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID | None = None
    integration_id: uuid.UUID | None = None
    provider_message_id: str
    thread_id: str | None = None
    sender: str
    sender_domain: str | None = None
    recipient: str | None = None
    subject: str = ""
    snippet: str | None = None
    body_text: str | None = None
    received_at: datetime
    classification: EmailClassification
    classification_confidence: float | None = None
    classified_by: str | None = None
    classification_reason: str | None = None
    matched_by: str | None = None
    is_simulated: bool = False
    is_read: bool = False
    status_applied: bool = False
    created_at: datetime | None = None


class EmailLinkRequest(BaseModel):
    """``POST /emails/{id}/link`` — attach a message to one of the user's applications."""

    application_id: uuid.UUID


class EmailClassifyRequest(BaseModel):
    """``POST /emails/{id}/classify`` — manual override of the classifier."""

    classification: EmailClassification


class EmailSimulateRequest(BaseModel):
    """``POST /emails/simulate`` — inject a realistic demo email without Gmail."""

    application_id: uuid.UUID | None = None
    kind: EmailClassification = EmailClassification.APPLICATION_RECEIVED
    subject: str | None = Field(default=None, max_length=1000)
    body: str | None = None
    sender: str | None = Field(default=None, max_length=500)


__all__ = [
    "EmailClassifyRequest",
    "EmailLinkRequest",
    "EmailMessageRead",
    "EmailSimulateRequest",
    "IncomingEmail",
    "LIST_BODY_LIMIT",
]
