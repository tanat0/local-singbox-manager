from __future__ import annotations

import logging
import sys


def setup_logging() -> None:
    """
    Configure application-wide logging.

    Rules:
    - INFO  for significant operations (deploy start/ok, service control, startup)
    - WARNING for degraded conditions (deploy fail, rollback, health degraded)
    - ERROR  for unrecoverable failures
    - No DEBUG — avoid log spam in a local daemon
    """
    fmt = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    # Suppress chatty third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("alembic.runtime.migration").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
