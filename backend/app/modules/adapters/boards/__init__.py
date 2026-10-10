"""Real job discovery from the public job board APIs of four ATS vendors.

=================  ==================================================================
Adapter            Endpoint (public, documented, unauthenticated)
=================  ==================================================================
Greenhouse         ``boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true``
Lever              ``api.lever.co/v0/postings/{token}?mode=json``
Ashby              ``api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true``
SmartRecruiters    ``api.smartrecruiters.com/v1/companies/{token}/postings`` (+ ``/{id}``)
=================  ==================================================================

Which boards are read comes from the company registry (``companies.ats_type`` +
``companies.ats_board_token``), passed in through ``SearchQuery.board_tokens``. The
apply side is the shared hosted-form flow of ``GenericAtsFormAdapter``.
"""
from __future__ import annotations

from app.models.enums import JobSourceType
from app.modules.adapters.boards.ashby import AshbyAdapter
from app.modules.adapters.boards.common import BoardAdapter
from app.modules.adapters.boards.greenhouse import GreenhouseAdapter
from app.modules.adapters.boards.http import BoardFetchError, BoardNotFound, BoardPayloadError
from app.modules.adapters.boards.lever import LeverAdapter
from app.modules.adapters.boards.smartrecruiters import SmartRecruitersAdapter
from app.modules.adapters.boards.urls import BOARD_VENDORS, BoardUrlError, infer_ats_type, parse_board_url, public_board_url

#: The board sources, in presentation order.
BOARD_SOURCES: tuple[JobSourceType, ...] = BOARD_VENDORS

__all__ = [
    "AshbyAdapter",
    "BOARD_SOURCES",
    "BoardAdapter",
    "BoardFetchError",
    "BoardNotFound",
    "BoardPayloadError",
    "BoardUrlError",
    "GreenhouseAdapter",
    "LeverAdapter",
    "SmartRecruitersAdapter",
    "infer_ats_type",
    "parse_board_url",
    "public_board_url",
]
