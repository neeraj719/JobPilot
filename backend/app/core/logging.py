"""Structured (JSON) logging configuration."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from app.core.config import settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("user_id", "application_id", "run_id", "request_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    if settings.ENV == "development":
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    else:
        handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL.upper())
    for noisy in ("uvicorn.access", "httpx", "httpcore", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
