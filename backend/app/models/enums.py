"""All domain enums in one place so every module shares the same vocabulary."""
from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover
        return str(self.value)


class UserRole(StrEnum):
    USER = "USER"
    ADMIN = "ADMIN"


class WorkMode(StrEnum):
    REMOTE = "REMOTE"
    HYBRID = "HYBRID"
    ONSITE = "ONSITE"


class EmploymentType(StrEnum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT = "CONTRACT"
    INTERNSHIP = "INTERNSHIP"
    FREELANCE = "FREELANCE"


class ExperienceLevel(StrEnum):
    INTERN = "INTERN"
    ENTRY = "ENTRY"
    MID = "MID"
    SENIOR = "SENIOR"
    LEAD = "LEAD"
    PRINCIPAL = "PRINCIPAL"


class CompanyPriority(StrEnum):
    P1 = "P1"  # top priority (e.g. Google, Microsoft, Amazon)
    P2 = "P2"  # normal priority
    P3 = "P3"  # low priority (e.g. startups) — still applied to
    AVOID = "AVOID"  # never apply


class JobSourceType(StrEnum):
    NAUKRI = "NAUKRI"
    INDEED = "INDEED"
    LINKEDIN = "LINKEDIN"
    HIRIST = "HIRIST"
    WELLFOUND = "WELLFOUND"
    INTERNSHALA = "INTERNSHALA"
    GLASSDOOR = "GLASSDOOR"
    FOUNDIT = "FOUNDIT"
    COMPANY_CAREERS = "COMPANY_CAREERS"
    GREENHOUSE = "GREENHOUSE"
    LEVER = "LEVER"
    WORKDAY = "WORKDAY"
    DEMO_ATS = "DEMO_ATS"  # local mock ATS served by this backend for the Playwright demo
    OTHER = "OTHER"


class ApplicationType(StrEnum):
    EASY_APPLY = "EASY_APPLY"  # one-click apply inside the platform
    EXTERNAL_FORM = "EXTERNAL_FORM"  # redirect to company website form
    ATS_FORM = "ATS_FORM"  # Greenhouse/Lever/Workday style form
    EMAIL = "EMAIL"
    UNKNOWN = "UNKNOWN"


class ApplicationStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    APPLIED = "APPLIED"
    APPLICATION_RECEIVED = "APPLICATION_RECEIVED"
    ASSESSMENT = "ASSESSMENT"
    INTERVIEW = "INTERVIEW"
    RECRUITER_CONTACTED = "RECRUITER_CONTACTED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    OFFER = "OFFER"
    NO_RESPONSE = "NO_RESPONSE"
    SKIPPED = "SKIPPED"


# Statuses that count as "a response from the company" for analytics.
RESPONSE_STATUSES = {
    ApplicationStatus.APPLICATION_RECEIVED,
    ApplicationStatus.ASSESSMENT,
    ApplicationStatus.INTERVIEW,
    ApplicationStatus.RECRUITER_CONTACTED,
    ApplicationStatus.REJECTED,
    ApplicationStatus.OFFER,
}

# Statuses meaning an application has actually been sent.
SUBMITTED_STATUSES = RESPONSE_STATUSES | {ApplicationStatus.APPLIED, ApplicationStatus.NO_RESPONSE, ApplicationStatus.WITHDRAWN}


class AutomationState(StrEnum):
    """State of the automation attached to an application (see spec §28)."""

    IDLE = "IDLE"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PAUSED = "PAUSED"
    REQUIRES_USER = "REQUIRES_USER"
    RETRYING = "RETRYING"


class PauseReason(StrEnum):
    CAPTCHA = "CAPTCHA"
    OTP = "OTP"
    TWO_FACTOR = "TWO_FACTOR"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    ACCOUNT_REGISTRATION_REQUIRED = "ACCOUNT_REGISTRATION_REQUIRED"
    UNKNOWN_QUESTION = "UNKNOWN_QUESTION"
    LEGAL_DECLARATION = "LEGAL_DECLARATION"
    WORK_AUTHORIZATION = "WORK_AUTHORIZATION"
    DEMOGRAPHIC_QUESTION = "DEMOGRAPHIC_QUESTION"
    USER_REVIEW = "USER_REVIEW"
    WEBSITE_CHANGED = "WEBSITE_CHANGED"
    OTHER = "OTHER"


class AnswerSource(StrEnum):
    PROFILE = "PROFILE"
    RESUME = "RESUME"
    PREFERENCE = "PREFERENCE"
    AI_GENERATED = "AI_GENERATED"
    USER = "USER"
    DEFAULT = "DEFAULT"


class AnswerStatus(StrEnum):
    ANSWERED = "ANSWERED"
    NEEDS_USER_INPUT = "NEEDS_USER_INPUT"
    SKIPPED = "SKIPPED"


class FieldType(StrEnum):
    TEXT = "TEXT"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    NUMBER = "NUMBER"
    TEXTAREA = "TEXTAREA"
    SELECT = "SELECT"
    RADIO = "RADIO"
    CHECKBOX = "CHECKBOX"
    FILE = "FILE"
    DATE = "DATE"
    URL = "URL"
    HIDDEN = "HIDDEN"
    UNKNOWN = "UNKNOWN"


class ApplicationEventType(StrEnum):
    CREATED = "CREATED"
    STATUS_CHANGED = "STATUS_CHANGED"
    AUTOMATION = "AUTOMATION"
    ANSWERS_GENERATED = "ANSWERS_GENERATED"
    FORM_FILLED = "FORM_FILLED"
    PAUSED = "PAUSED"
    RESUMED = "RESUMED"
    APPROVED = "APPROVED"
    SUBMITTED = "SUBMITTED"
    EMAIL_LINKED = "EMAIL_LINKED"
    NOTE = "NOTE"
    USER_ACTION = "USER_ACTION"
    ERROR = "ERROR"


class Actor(StrEnum):
    SYSTEM = "SYSTEM"
    USER = "USER"
    AUTOMATION = "AUTOMATION"
    EMAIL = "EMAIL"
    SCHEDULER = "SCHEDULER"


class DocumentType(StrEnum):
    RESUME = "RESUME"
    COVER_LETTER = "COVER_LETTER"
    OTHER = "OTHER"


class ResumeParseStatus(StrEnum):
    PENDING = "PENDING"
    PARSED = "PARSED"
    FAILED = "FAILED"


class EmailProvider(StrEnum):
    GMAIL = "GMAIL"


class IntegrationStatus(StrEnum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"


class EmailClassification(StrEnum):
    APPLICATION_RECEIVED = "APPLICATION_RECEIVED"
    RECRUITER_MESSAGE = "RECRUITER_MESSAGE"
    INTERVIEW = "INTERVIEW"
    ASSESSMENT = "ASSESSMENT"
    REJECTION = "REJECTION"
    OFFER = "OFFER"
    OTHER = "OTHER"


# Which application status an email classification implies.
CLASSIFICATION_TO_STATUS = {
    EmailClassification.APPLICATION_RECEIVED: ApplicationStatus.APPLICATION_RECEIVED,
    EmailClassification.RECRUITER_MESSAGE: ApplicationStatus.RECRUITER_CONTACTED,
    EmailClassification.INTERVIEW: ApplicationStatus.INTERVIEW,
    EmailClassification.ASSESSMENT: ApplicationStatus.ASSESSMENT,
    EmailClassification.REJECTION: ApplicationStatus.REJECTED,
    EmailClassification.OFFER: ApplicationStatus.OFFER,
}


class InterviewType(StrEnum):
    PHONE_SCREEN = "PHONE_SCREEN"
    TECHNICAL = "TECHNICAL"
    SYSTEM_DESIGN = "SYSTEM_DESIGN"
    BEHAVIORAL = "BEHAVIORAL"
    HR = "HR"
    ONSITE = "ONSITE"
    ASSESSMENT = "ASSESSMENT"
    OTHER = "OTHER"


class InterviewStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    RESCHEDULED = "RESCHEDULED"


class AutomationRunTrigger(StrEnum):
    SCHEDULED = "SCHEDULED"
    MANUAL = "MANUAL"


class AutomationRunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"


class NotificationType(StrEnum):
    JOB_FOUND = "JOB_FOUND"
    INPUT_REQUIRED = "INPUT_REQUIRED"
    APPLICATION_SUBMITTED = "APPLICATION_SUBMITTED"
    RECRUITER_RESPONSE = "RECRUITER_RESPONSE"
    INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED"
    ASSESSMENT_RECEIVED = "ASSESSMENT_RECEIVED"
    REJECTION = "REJECTION"
    OFFER = "OFFER"
    AUTOMATION_FAILED = "AUTOMATION_FAILED"
    AUTOMATION_COMPLETED = "AUTOMATION_COMPLETED"
    SYSTEM = "SYSTEM"


class AuditLevel(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class BrowserSessionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
