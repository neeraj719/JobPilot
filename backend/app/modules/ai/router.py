"""AI router — mounted at ``/api/v1/ai`` by ``app.main`` (CONTRACTS.md §6)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.models.user import User
from app.modules.ai.factory import provider_status
from app.modules.ai.schemas import AIStatus

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status", response_model=AIStatus, summary="Which LLM provider is active")
def get_status(user: User = Depends(get_current_user)) -> AIStatus:
    """Report the configured provider/model and whether it has credentials.

    ``configured`` is always true for the mock provider — the app is fully usable
    without any API key.
    """
    return AIStatus.model_validate(provider_status())
