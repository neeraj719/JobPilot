"""Gmail OAuth + connected job-platform accounts.

``sync_all_connected`` is the entry point the worker's hourly job calls.
"""
from app.modules.integrations.service import sync_all_connected, sync_gmail

__all__ = ["sync_all_connected", "sync_gmail"]
