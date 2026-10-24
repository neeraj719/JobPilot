"""Whose AI settings apply to the current call (plan contract §4.4).

``app.modules.ai.runtime`` resolves the provider/model for *the current user*. It finds
that user here, without any function in between having to pass it along:

1. :func:`ai_user` — an explicit block, for background work::

       with ai_user(user_id):
           analyse_in_a_thread(...)

2. the authenticated user of the current HTTP request, published by
   ``app.core.deps.get_current_user``;
3. the actor of background work that already runs under ``app.core.actor.actor_context``
   (the automation pipeline, the application executor), so existing jobs honour the
   user's choice without changes;
4. otherwise nobody: the server default (``settings.LLM_PROVIDER``) applies.

Why a mutable slot rather than a plain ``ContextVar[UUID]``
------------------------------------------------------------
Starlette runs every sync dependency and sync endpoint in a *copy* of the request's
context (see ``app.core.actor``), so a value ``set()`` inside ``get_current_user`` would
be gone by the time the endpoint runs. :func:`request_ai_context` is an ``async`` dependency
— it runs in the request's own task — and publishes a fresh :class:`AiUserSlot` there;
``get_current_user`` (in its thread) only *mutates* that object, and every later copy of the
context sees the same object. Each request is its own task, so slots never leak between
requests, and the slot is emptied when the request ends.

This module imports nothing but the standard library: ``app.core.deps`` imports it.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any


class AiUserSlot:
    """Mutable holder for the user id of one request (or one ``ai_user`` block).

    ``target_override`` is the model the user picked for *this run* (the "which model should
    process this?" choice, ``ai.choice``): an ``ai.routing.Target`` validated by
    ``ai.choice.validate_choice``. ``ai.runtime.resolve_current`` returns it with
    ``source="per_run"`` for every task of the request, so no call site changes.
    """

    __slots__ = ("user_id", "target_override")

    def __init__(self, user_id: uuid.UUID | None = None, target_override: Any = None) -> None:
        self.user_id = user_id
        self.target_override = target_override

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AiUserSlot {self.user_id} {self.target_override}>"


_slot: ContextVar[AiUserSlot | None] = ContextVar("jobpilot_ai_user_slot", default=None)


def _coerce(user_id: uuid.UUID | str | None) -> uuid.UUID | None:
    if user_id is None or isinstance(user_id, uuid.UUID):
        return user_id
    return uuid.UUID(str(user_id))


def current_ai_user() -> uuid.UUID | None:
    """The user whose AI settings apply right now, or ``None`` for the server default."""
    slot = _slot.get()
    if slot is not None and slot.user_id is not None:
        return slot.user_id
    try:  # background work published through app.core.actor.actor_context
        from app.core.actor import get_actor

        return get_actor()
    except Exception:  # pragma: no cover - defensive, the actor module always exists
        return None


def current_target_override() -> Any:
    """The per-run model choice of the current request / block (``ai.routing.Target``) or ``None``."""
    slot = _slot.get()
    return slot.target_override if slot is not None else None


def set_target_override(target: Any) -> bool:
    """Publish ``target`` as this request's per-run model (``ai.choice.apply_choice``).

    Returns ``False`` when there is no slot (outside a request or ``ai_user`` block), in
    which case nothing is changed.
    """
    slot = _slot.get()
    if slot is None:
        return False
    slot.target_override = target
    return True


@contextmanager
def ai_user(user_id: uuid.UUID | str | None, *, target_override: Any = None) -> Iterator[None]:
    """Run a block with ``user_id``'s AI settings (threads, workers, scripts).

    Set and reset happen in the same context, so nesting and threads are safe. A thread
    started with ``threading.Thread`` starts with an *empty* context: wrap the thread's
    target in this, not the code that starts it. ``target_override`` carries a per-run
    model choice into background work (capture it with :func:`current_target_override`
    before starting the thread).
    """
    token = _slot.set(AiUserSlot(_coerce(user_id), target_override))
    try:
        yield
    finally:
        _slot.reset(token)


async def request_ai_context() -> AsyncIterator[AiUserSlot]:
    """FastAPI dependency (async on purpose, see the module docstring): publish an empty
    slot for this request and empty it again when the request is over."""
    slot = AiUserSlot()
    token = _slot.set(slot)
    try:
        yield slot
    finally:
        slot.user_id = None
        slot.target_override = None
        try:
            _slot.reset(token)
        except ValueError:  # torn down in another context: the emptied slot is harmless
            pass


def bind_request_user(slot: AiUserSlot | None, user_id: uuid.UUID | None) -> None:
    """Called by ``get_current_user`` once the user is authenticated."""
    if isinstance(slot, AiUserSlot):
        slot.user_id = user_id


__all__ = [
    "AiUserSlot",
    "ai_user",
    "bind_request_user",
    "current_ai_user",
    "current_target_override",
    "request_ai_context",
    "set_target_override",
]
