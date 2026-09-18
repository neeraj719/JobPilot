"""Import every model so ``Base.metadata`` is complete for Alembic and tests."""
from app.models.application import Application, ApplicationAnswer, ApplicationDocument, ApplicationEvent
from app.models.audit import AuditLog
from app.models.automation import AutomationConfig, AutomationRun, BrowserSession, ConnectedAccount
from app.models.base import Base
from app.models.company import Company
from app.models.email import EmailIntegration, EmailMessage
from app.models.enums import *  # noqa: F401,F403
from app.models.interview import Interview
from app.models.job import Job, JobMatch, JobSource
from app.models.notification import Notification
from app.models.profile import CompanyPreference, JobPreference, UserProfile
from app.models.resume import Resume, ResumeVersion, Skill
from app.models.user import RefreshToken, User

__all__ = [
    "Base",
    "User",
    "RefreshToken",
    "UserProfile",
    "JobPreference",
    "CompanyPreference",
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
