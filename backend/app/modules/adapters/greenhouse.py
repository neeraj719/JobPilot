"""Greenhouse adapter - the real implementation lives in :mod:`app.modules.adapters.boards.greenhouse`.

Kept as an import path so ``from app.modules.adapters.greenhouse import GreenhouseAdapter``
keeps working.
"""
from __future__ import annotations

from app.modules.adapters.boards.greenhouse import GreenhouseAdapter

__all__ = ["GreenhouseAdapter"]
