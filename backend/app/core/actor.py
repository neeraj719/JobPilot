"""Who is writing: the actor behind ``created_by`` / ``updated_by``.

Every row carries the user who created it and the user who last changed it
(:class:`app.models.base.AuditUserMixin`). Nothing in the service layer sets those
columns by hand — eighteen modules each remembering two assignments is eighteen chances
to forget one. Instead the acting user is published once, at the entry point, and two
flush listeners stamp every row on its way into the database.

``NULL`` is a real answer: it means *no user did this*. A scheduler tick, a migration, a
seed run and a webhook are system writes, and they are supposed to read as such.

Two ways to publish the actor
-----------------------------
``set_actor`` / :func:`actor_context` set a :class:`~contextvars.ContextVar`. This is the
mechanism for **background work** — a thread running the automation pipeline, a worker
job, a script — where the entry point knows whose behalf it is acting on and everything
below it is ordinary function calls.

:func:`set_session_actor` records the actor on the ``Session`` instead, and that is the
mechanism for **HTTP requests** (``app.core.deps.get_current_user``). A ContextVar set
inside a FastAPI dependency would not reach the endpoint: Starlette runs every sync
dependency and every sync endpoint through ``anyio.to_thread.run_sync``, which executes
them in a *copy* of the request's context, so the write is discarded when the dependency
returns (and ``ContextVar.reset`` in a ``yield`` dependency raises outright, because
``__enter__`` and ``__exit__`` land in two different contexts). The session, on the other
hand, is the same object the endpoint writes through and its lifetime is exactly the
transaction being stamped, which makes it the more honest carrier anyway.

:class:`ActorMiddleware` closes the gap in the other direction: it runs as plain ASGI, in
the request's own context, so ``get_actor()`` is also correct inside a request for code
that is nowhere near the session. Both sources agree; the ContextVar wins when both are
set, because setting it is always a deliberate, narrower statement (``create_user``
wrapping the rows it builds for the account being registered, for instance).
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session, object_session

#: The user on whose behalf the current call stack is writing, or ``None`` for a system
#: write. Read through :func:`get_actor`; set through :func:`set_actor` / :func:`actor_context`.
current_actor_id: ContextVar[uuid.UUID | None] = ContextVar("current_actor_id", default=None)

#: Key under which the request's actor is recorded in ``Session.info``.
SESSION_ACTOR_KEY = "actor_id"


def set_actor(user_id: uuid.UUID | None) -> Token:
    """Publish ``user_id`` as the actor for this context. Returns the reset token."""
    return current_actor_id.set(user_id)


def reset_actor(token: Token) -> None:
    """Undo a :func:`set_actor`, in the same context that made it."""
    current_actor_id.reset(token)


def get_actor() -> uuid.UUID | None:
    return current_actor_id.get()


@contextmanager
def actor_context(user_id: uuid.UUID | None) -> Iterator[None]:
    """Run a block as ``user_id``::

        with actor_context(user_id):
            run_pipeline(user_id)

    Set and reset happen in the same context, which is what makes this safe where a
    ``yield`` dependency is not.
    """
    token = set_actor(user_id)
    try:
        yield
    finally:
        reset_actor(token)


def set_session_actor(session: Session, user_id: uuid.UUID | None) -> None:
    """Record the actor on a session, for everything that session flushes."""
    session.info[SESSION_ACTOR_KEY] = user_id


def session_actor(session: Session | None) -> uuid.UUID | None:
    if session is None:
        return None
    return session.info.get(SESSION_ACTOR_KEY)


def resolve_actor(session: Session | None = None) -> uuid.UUID | None:
    """The actor to stamp: the ContextVar if one is set, else the session's, else ``None``."""
    actor = get_actor()
    if actor is not None:
        return actor
    return session_actor(session)


# --------------------------------------------------------------------------- stamping


def _stamp_insert(mapper: Any, connection: Any, target: Any) -> None:
    """``created_by`` and ``updated_by`` on INSERT.

    An explicitly supplied ``created_by`` is never overwritten — ``app/seed.py``
    fabricates history and owns the attribution of the rows it writes.
    """
    actor = resolve_actor(object_session(target))
    if actor is None:
        return
    if target.created_by is None:
        target.created_by = actor
    if target.updated_by is None:
        target.updated_by = actor


def _stamp_update(mapper: Any, connection: Any, target: Any) -> None:
    """``updated_by`` on UPDATE — but only when the row is really changing.

    ``before_update`` fires for every dirty object, including ones whose net change is
    nothing. Stamping those would turn a no-op into a real UPDATE, which the
    ``updated_at`` trigger would then rightly treat as a modification.
    """
    session = object_session(target)
    if session is not None and not session.is_modified(target, include_collections=False):
        return
    actor = resolve_actor(session)
    if actor is None:
        return
    if target.updated_by != actor:
        target.updated_by = actor


def register_actor_stamping() -> None:
    """Attach the two listeners to :class:`~app.models.base.AuditUserMixin`.

    ``propagate=True`` is what makes one registration on the unmapped mixin cover all 27
    mapped classes, now and whenever the 28th is added.
    """
    from app.models.base import AuditUserMixin

    if not event.contains(AuditUserMixin, "before_insert", _stamp_insert):
        event.listen(AuditUserMixin, "before_insert", _stamp_insert, propagate=True)
    if not event.contains(AuditUserMixin, "before_update", _stamp_update):
        event.listen(AuditUserMixin, "before_update", _stamp_update, propagate=True)


register_actor_stamping()


# --------------------------------------------------------------------------- HTTP


def _actor_from_headers(headers: list) -> uuid.UUID | None:
    raw = next((value for key, value in headers if key.lower() == b"authorization"), None)
    if not raw:
        return None
    try:
        scheme, _, credentials = raw.decode("latin-1").partition(" ")
    except Exception:  # pragma: no cover - defensive
        return None
    if scheme.lower() != "bearer" or not credentials.strip():
        return None
    from app.core.security import decode_access_token

    try:
        return uuid.UUID(decode_access_token(credentials.strip())["sub"])
    except Exception:
        return None


class ActorMiddleware:
    """Publish the bearer token's subject as the actor for the whole request.

    Plain ASGI on purpose: it runs in the request's own context, so the ContextVar it
    sets is visible to everything downstream, including the threadpool that runs sync
    endpoints (a child context inherits what was set before it was copied — it is only
    writes made *inside* the copy that are lost).

    It trusts nothing: the token is verified exactly as ``get_current_user`` verifies it,
    and an invalid, expired or absent token simply leaves the actor unset. It does not
    check that the user still exists or is active — ``get_current_user`` does that, and a
    request that fails there never reaches code that writes.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        token = set_actor(_actor_from_headers(scope.get("headers") or []))
        try:
            await self.app(scope, receive, send)
        finally:
            reset_actor(token)


__all__ = [
    "ActorMiddleware",
    "SESSION_ACTOR_KEY",
    "actor_context",
    "current_actor_id",
    "get_actor",
    "register_actor_stamping",
    "reset_actor",
    "resolve_actor",
    "session_actor",
    "set_actor",
    "set_session_actor",
]
