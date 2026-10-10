"""Import every model so ``Base.metadata`` is complete for Alembic and tests."""
from app.models.application import Application, ApplicationAnswer, ApplicationDocument, ApplicationEvent
from app.models.audit import AuditLog
from app.models.automation import AutomationConfig, AutomationRun, BrowserSession, ConnectedAccount
from app.models.base import (
    SCHEMA_AUDIT,
    SCHEMA_MASTER,
    SCHEMA_MEDIA,
    SCHEMA_TRANSACTION,
    SCHEMA_UNIFIED,
    SCHEMAS,
    SQLITE_SCHEMA_TRANSLATE_MAP,
    AuditUserMixin,
    Base,
    LifecycleMixin,
    StandardColumnsMixin,
)
from app.models.company import Company
from app.models.email import EmailIntegration, EmailMessage
from app.models.enums import *  # noqa: F401,F403
from app.models.interview import Interview
from app.models.job import Job, JobMatch, JobSource
from app.models.notification import Notification
from app.models.profile import CompanyPreference, JobPreference, StandingAnswer, UserProfile
from app.models.resume import Resume, ResumeVersion, Skill
from app.models.user import DEFAULT_ROLES, RefreshToken, Role, User, UserRoleAssignment

__all__ = [
    "Base",
    "AuditUserMixin",
    "LifecycleMixin",
    "StandardColumnsMixin",
    "SCHEMA_MASTER",
    "SCHEMA_UNIFIED",
    "SCHEMA_TRANSACTION",
    "SCHEMA_MEDIA",
    "SCHEMA_AUDIT",
    "SCHEMAS",
    "SQLITE_SCHEMA_TRANSLATE_MAP",
    "User",
    "Role",
    "DEFAULT_ROLES",
    "UserRoleAssignment",
    "RefreshToken",
    "UserProfile",
    "JobPreference",
    "CompanyPreference",
    "StandingAnswer",
    "Resume",
    "ResumeVersion",
    "Skill",
    "Company",
    "Job",
    "JobSource",
    "JobMatch",
    "Application",
    "ApplicationAnswer",
    "ApplicationEvent",
    "ApplicationDocument",
    "EmailIntegration",
    "EmailMessage",
    "Interview",
    "AutomationConfig",
    "AutomationRun",
    "ConnectedAccount",
    "BrowserSession",
    "AuditLog",
    "Notification",
]
