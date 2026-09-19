"""composite indexes for the hot list/aggregate queries

Every one of these backs a query the API runs on every page load, and each is a
compound of "the owning user" plus the column the query filters or sorts on. The
single-column indexes created by the initial migration stay: PostgreSQL still uses
them for the lookups that do not carry a user predicate (e.g. ``audit_logs.action``).

Written by hand (no ``batch_alter_table``) so it runs unchanged on PostgreSQL and
SQLite — same rule as the initial migration.

Revision ID: a1c4f7b28e10
Revises: 631b510744ed
Create Date: 2026-09-19
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1c4f7b28e10'
down_revision: Union[str, None] = '631b510744ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: ``(index name, table, columns)`` — kept as data so upgrade/downgrade cannot drift.
INDEXES: tuple[tuple[str, str, list[str]], ...] = (
    # GET /applications/queue, GET /applications?status=, the review summary.
    ("ix_applications_user_status", "applications", ["user_id", "status"]),
    # automation.limits.submitted_today + dashboard "applications today".
    ("ix_applications_user_applied_at", "applications", ["user_id", "applied_at"]),
    # GET /applications/{id}/events and the activity feed.
    ("ix_application_events_application_created", "application_events", ["application_id", "created_at"]),
    # GET /matching/summary and the job list's score sort.
    ("ix_job_matches_user_score", "job_matches", ["user_id", "match_score"]),
    # GET /emails (newest first, per user).
    ("ix_email_messages_user_received_at", "email_messages", ["user_id", "received_at"]),
    # GET /audit and GET /dashboard/activity (newest first, per user).
    ("ix_audit_logs_user_created_at", "audit_logs", ["user_id", "created_at"]),
    # GET /notifications?unread_only= (newest first, per user).
    ("ix_notifications_user_read_created", "notifications", ["user_id", "is_read", "created_at"]),
    # Dashboard "interviews in the next 7 days".
    ("ix_interviews_user_scheduled_at", "interviews", ["user_id", "scheduled_at"]),
)


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns, unique=False)


def downgrade() -> None:
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
