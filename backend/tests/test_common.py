"""Tests for the shared pagination / envelope primitives (contract §0)."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import NotificationType
from app.models.notification import Notification
from app.modules.common import OkResponse, PageResponse, Pagination, paginate, paginate_sequence
from app.modules.notifications.service import notify


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """The API rate limiter is process-wide; keep test runs independent of it."""
    from app.core.rate_limit import rate_limiter

    hits = getattr(rate_limiter._backend, "_hits", None)
    if hits is not None:
        hits.clear()
    yield


def _make_user(db: Session, email: str = "pager@example.com"):
    from app.modules.auth.service import create_user

    user = create_user(db, email, "StrongPass123", "Page Tester")
    db.commit()
    return user


def test_page_response_shape_and_pages() -> None:
    page = PageResponse[int](items=[1, 2, 3], total=7, page=1, page_size=3)
    assert page.model_dump() == {"items": [1, 2, 3], "total": 7, "page": 1, "page_size": 3}
    assert page.pages == 3


def test_ok_response_defaults() -> None:
    assert OkResponse().model_dump() == {"ok": True, "message": None}


def test_pagination_offsets() -> None:
    assert Pagination(page=1, page_size=20).offset == 0
    assert Pagination(page=3, page_size=20).offset == 40
    assert Pagination(page=3, page_size=20).limit == 20


def test_paginate_counts_total_and_slices(db: Session) -> None:
    user = _make_user(db)
    for i in range(7):
        notify(db, user.id, NotificationType.SYSTEM, f"Notification {i}")
    db.commit()

    stmt = select(Notification).where(Notification.user_id == user.id).order_by(Notification.title.asc())
    page = paginate(db, stmt, Pagination(page=2, page_size=3))
    assert page.total == 7
    assert page.page == 2
    assert len(page.items) == 3
    assert [n.title for n in page.items] == ["Notification 3", "Notification 4", "Notification 5"]

    last = paginate(db, stmt, Pagination(page=3, page_size=3))
    assert len(last.items) == 1


def test_paginate_transform_maps_rows(db: Session) -> None:
    user = _make_user(db, "pager2@example.com")
    notify(db, user.id, NotificationType.SYSTEM, "Hello")
    db.commit()

    stmt = select(Notification).where(Notification.user_id == user.id)
    page = paginate(db, stmt, Pagination(page=1, page_size=10), transform=lambda row: row.title)
    assert page.items == ["Hello"]


def test_paginate_keeps_duplicate_scalar_values(db: Session) -> None:
    user = _make_user(db, "pager3@example.com")
    for _ in range(3):
        notify(db, user.id, NotificationType.SYSTEM, "Same title")
    db.commit()

    stmt = select(Notification.title).where(Notification.user_id == user.id)
    page = paginate(db, stmt, Pagination(page=1, page_size=10))
    assert page.total == 3
    assert page.items == ["Same title", "Same title", "Same title"]


def test_paginate_sequence() -> None:
    page = paginate_sequence(list(range(10)), Pagination(page=2, page_size=4))
    assert page.items == [4, 5, 6, 7]
    assert page.total == 10


def test_list_endpoint_rejects_out_of_range_pagination(auth_client: TestClient) -> None:
    assert auth_client.get("/api/v1/notifications", params={"page": 0}).status_code == 422
    assert auth_client.get("/api/v1/notifications", params={"page_size": 0}).status_code == 422
    assert auth_client.get("/api/v1/notifications", params={"page_size": 101}).status_code == 422

    ok = auth_client.get("/api/v1/notifications", params={"page": 1, "page_size": 100})
    assert ok.status_code == 200
    body = ok.json()
    assert set(body) == {"items", "total", "page", "page_size"}
    assert body["page_size"] == 100


def test_error_envelope_shape(auth_client: TestClient) -> None:
    response = auth_client.get(f"/api/v1/companies/{uuid.uuid4()}")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert isinstance(error["message"], str)
