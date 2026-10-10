"""Soft delete: one tombstone column, one global filter, one escape hatch.

Deleting a row in JobPilot does not issue a ``DELETE``. It sets the two lifecycle
columns every table carries (:class:`app.models.base.LifecycleMixin`)::

    deleted_at = now()     # the tombstone: the row must behave as if it were gone
    is_active  = False     # a deleted row is never also "active"

Making the row *behave* as gone is the hard half, and it is done exactly once, here. A
``do_orm_execute`` listener on :class:`~sqlalchemy.orm.Session` appends

    with_loader_criteria(LifecycleMixin, lambda cls: cls.deleted_at.is_(None))

to every ORM SELECT. Because the criteria targets the **mixin**, it applies to all 27
mapped classes at once, and because ``include_aliases=True`` it also applies to aliased
copies pulled in by joined/selectin eager loads. ``propagate_to_loaders`` (the default)
carries it onto subsequent lazy relationship loads of the objects a query returned, so
``user.resumes`` hides tombstones just as ``select(Resume)`` does — and ``Session.get``
is an ORM SELECT like any other, so a soft-deleted user simply is not found.

This is why no module filters on ``deleted_at`` by hand. Eighteen modules each
remembering a ``.where(...)`` is eighteen chances to forget one, and the one that is
forgotten is a data leak rather than a cosmetic bug.

The escape hatch is explicit and per statement::

    db.scalars(select(Resume).execution_options(include_deleted=True))
    db.get(User, user_id, execution_options={"include_deleted": True})

Use it only where tombstones are the point: an admin/debug view, or a rebuild tool such
as ``app/seed.py --force`` which has to find and hard-delete them.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from app.models.base import LifecycleMixin, utcnow

#: Execution option that turns the global filter off for one statement.
INCLUDE_DELETED = "include_deleted"


def soft_delete(obj: LifecycleMixin, *, when: datetime | None = None) -> LifecycleMixin:
    """Tombstone ``obj``: set ``deleted_at`` and clear ``is_active``.

    Idempotent — re-deleting an already deleted row keeps the original timestamp, so the
    audit answer to "when did this go away" does not move. The caller owns the flush, so
    a delete can take part in the same transaction as the audit entry that records it.
    """
    if obj.deleted_at is None:
        obj.deleted_at = when or utcnow()
    obj.is_active = False
    return obj


def restore(obj: LifecycleMixin, *, reactivate: bool = True) -> LifecycleMixin:
    """Undo :func:`soft_delete`. Used when a user re-creates something they deleted."""
    obj.deleted_at = None
    if reactivate:
        obj.is_active = True
    return obj


def is_deleted(obj: LifecycleMixin) -> bool:
    return obj.deleted_at is not None


@event.listens_for(Session, "do_orm_execute")
def _filter_soft_deleted(execute_state: ORMExecuteState) -> None:
    """Append ``deleted_at IS NULL`` to every ORM SELECT that did not opt out.

    ``is_column_load`` (a deferred/expired attribute being refreshed) and
    ``is_relationship_load`` (a lazy load from an object that was itself loaded under the
    criteria) are secondary loads: they already inherit the criteria from the statement
    that produced the parent, and adding it a second time would only duplicate the
    predicate — or, for a column refresh, filter a row we are already holding.
    """
    if not execute_state.is_select:
        return
    if execute_state.is_column_load or execute_state.is_relationship_load:
        return
    if execute_state.execution_options.get(INCLUDE_DELETED, False):
        return
    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(LifecycleMixin, lambda cls: cls.deleted_at.is_(None), include_aliases=True)
    )
