"""JSON logs, one line per event, carrying the request id (SPEC §15)."""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Loggers whose own handlers would print plain text next to ours.
THIRD_PARTY = ("uvicorn", "uvicorn.error", "alembic")
# Replaced by plot.access, which carries the request id.
SILENCED = ("uvicorn.access",)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or request_id_var.get()
        if request_id:
            entry["request_id"] = request_id
        for key in ("method", "path", "status", "duration_ms"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_json_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in THIRD_PARTY:
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    for name in SILENCED:
        logging.getLogger(name).disabled = True
    logging.getLogger("httpx").setLevel(logging.WARNING)
