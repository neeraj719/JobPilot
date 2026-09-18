from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.job import Job


class Company(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "companies"

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
    ats_type: Mapped[str | None] = mapped_column(String(50))  # GREENHOUSE / LEVER / WORKDAY / CUSTOM / DEMO_ATS
    tags: Mapped[list[Any]] = mapped_column(JSON, default=list)  # ["FAANG", "product", "startup", "service"]

    jobs: Mapped[list[Job]] = relationship(back_populates="company")
