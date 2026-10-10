"""Lever adapter - the real implementation lives in :mod:`app.modules.adapters.boards.lever`.

Kept as an import path so ``from app.modules.adapters.lever import LeverAdapter`` keeps working.
"""
from __future__ import annotations

from app.modules.adapters.boards.lever import LeverAdapter

__all__ = ["LeverAdapter"]
