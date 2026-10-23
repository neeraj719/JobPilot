from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SCHEMA_MASTER, SCHEMA_MEDIA, Base, StandardColumnsMixin, UTCDateTime
from app.models.enums import ResumeChangeSource, ResumeKind, ResumeParseStatus

if TYPE_CHECKING:
    from app.models.user import User


class Resume(StandardColumnsMixin, Base):
    __tablename__ = "resumes"
    __table_args__ = {"schema": SCHEMA_MEDIA}

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("master.users.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g. "Software Engineer - Backend"
    target_role: Mapped[str | None] = mapped_column(String(255))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # UPLOADED resumes keep the original file; CREATED / TAILORED ones only have ``parsed_data``
    # (exports are rendered from it), so the file columns are nullable.
    kind: Mapped[ResumeKind] = mapped_column(
        Enum(ResumeKind, native_enum=False, length=20), default=ResumeKind.UPLOADED, nullable=False
    )
    #: Layout used by the preview and the PDF/DOCX export (``resumes.templates``).
    template: Mapped[str] = mapped_column(String(40), default="classic", nullable=False)
    #: The resume a TAILORED resume was generated from; every version stays linked to its source.
    source_resume_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media.resumes.id", ondelete="SET NULL"), index=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    #: Editor autosave: unsaved structured data, promoted to a version when the user saves.
    draft_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    draft_saved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    file_path: Mapped[str | None] = mapped_column(String(1024))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)

    text_content: Mapped[str | None] = mapped_column(Text)
    # Structured JSON produced by the AI parser and editable by the user:
    # {name, email, phone, summary, skills[], experience[], education[], projects[], certifications[], total_experience_years}
    parsed_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    parse_status: Mapped[ResumeParseStatus] = mapped_column(
        Enum(ResumeParseStatus, native_enum=False, length=20), default=ResumeParseStatus.PENDING, nullable=False
    )
    parse_error: Mapped[str | None] = mapped_column(Text)
    parsed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    user: Mapped[User] = relationship(back_populates="resumes", foreign_keys=lambda: [Resume.user_id])
    versions: Mapped[list[ResumeVersion]] = relationship(back_populates="resume", cascade="all, delete-orphan", order_by="ResumeVersion.version_number")
    source_resume: Mapped[Resume | None] = relationship(
        remote_side=lambda: [Resume.id], foreign_keys=lambda: [Resume.source_resume_id]
    )


class ResumeVersion(StandardColumnsMixin, Base):
    """Immutable history of a resume's file + parsed data."""

    __tablename__ = "resume_versions"
    __table_args__ = {"schema": SCHEMA_MEDIA}

    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("media.resumes.id", ondelete="CASCADE"), index=True, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(1024))
    parsed_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    note: Mapped[str | None] = mapped_column(String(500))
    #: USER (edited by hand), AI (generated/applied suggestion) or SYSTEM (upload, re-parse, restore).
    change_source: Mapped[ResumeChangeSource] = mapped_column(
        Enum(ResumeChangeSource, native_enum=False, length=20), default=ResumeChangeSource.USER, nullable=False
    )

    resume: Mapped[Resume] = relationship(back_populates="versions")


class Skill(StandardColumnsMixin, Base):
    """Lightweight skill taxonomy used for normalisation ("ReactJS" -> "React")."""

    __tablename__ = "skills"
    __table_args__ = {"schema": SCHEMA_MASTER}

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    aliases: Mapped[list[Any]] = mapped_column(JSON, default=list)
    category: Mapped[str | None] = mapped_column(String(80))  # language, framework, cloud, database, tool, soft
