"""
Structured logging configuration for ASDroid TikTok API.

Author: M.ASIM 🥰❤️👑
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar

# Per-request ID stored in a context variable
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Return the current request's ID, or generate one if unset."""
    rid = request_id_var.get()
    if not rid:
        rid = uuid.uuid4().hex[:12]
        request_id_var.set(rid)
    return rid


class RequestIDFilter(logging.Filter):
    """Injects request_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.request_id = get_request_id()
        return True


def configure_logging(level: str = "INFO") -> None:
    """Set up root logger with a structured text format.

    Args:
        level: Logging level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    fmt = (
        "%(asctime)s | %(levelname)-8s | %(request_id)s | "
        "%(name)s:%(lineno)d | %(message)s"
    )
    formatter = logging.Formatter(fmt, datefmt="%Y-%m-%dT%H:%M:%S")

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(RequestIDFilter())

    root = logging.getLogger()
    root.setLevel(numeric_level)
    # Avoid duplicate handlers if called multiple times (e.g. during tests)
    root.handlers.clear()
    root.addHandler(handler)

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger with the RequestIDFilter attached.

    Args:
        name: Logger name (typically __name__ of the calling module).

    Returns:
        Configured Logger instance.
    """
    logger = logging.getLogger(name)
    if not any(isinstance(f, RequestIDFilter) for f in logger.filters):
        logger.addFilter(RequestIDFilter())
    return logger
