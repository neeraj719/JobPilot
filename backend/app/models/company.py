from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.models.base import SCHEMA_MASTER, Base, StandardColumnsMixin

if TYPE_CHECKING:
    from app.models.job import Job


class Company(StandardColumnsMixin, Base):
    __tablename__ = "companies"
    __table_args__ = {"schema": SCHEMA_MASTER}

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255), index=True)  # e.g. google.com — used to link emails
    email_domains: Mapped[list[Any]] = mapped_column(JSON, default=list)  # extra sender domains (greenhouse-mail.io etc.)
    website: Mapped[str | None] = mapped_column(String(500))
    careers_url: Mapped[str | None] = mapped_column(String(500))
    logo_url: Mapped[str | None] = mapped_column(String(500))
    industry: Mapped[str | None] = mapped_column(String(120))
    size: Mapped[str | None] = mapped_column(String(50))  # "1-10", "11-50", ..., "10000+"
    headquarters: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    # A ``JobSourceType`` name: GREENHOUSE / LEVER / ASHBY / SMARTRECRUITERS / WORKDAY / CUSTOM / DEMO_ATS.
    ats_type: Mapped[str | None] = mapped_column(String(50))
    # The company's public job board on that ATS (Greenhouse "stripe", Lever "spotify", ...).
    # Set through ``PUT /companies/{id}/board``; the board adapters fetch every company that has one.
    ats_board_token: Mapped[str | None] = mapped_column(String(255))
    ats_board_url: Mapped[str | None] = mapped_column(String(500))  # the URL the token came from, for display
    tags: Mapped[list[Any]] = mapped_column(JSON, default=list)  # ["FAANG", "product", "startup", "service"]

    jobs: Mapped[list[Job]] = relationship(back_populates="company")

    @validates("ats_type")
    def _normalize_ats_type(self, _key: str, value: str | None) -> str | None:
        """Store ATS names exactly as the ``JobSourceType`` member names (``"smart recruiters"`` → ``SMARTRECRUITERS``)."""
        return normalize_ats_type(value)


def normalize_ats_type(value: str | None) -> str | None:
    """Canonical ``ats_type``: upper case, no spaces, dashes or underscores; blank → ``None``.

    ``DEMO_ATS`` is the one name with an underscore and keeps it.
    """
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    if text.replace("-", "_").replace(" ", "_") == "DEMO_ATS":
        return "DEMO_ATS"
    return text.replace(" ", "").replace("-", "").replace("_", "")
