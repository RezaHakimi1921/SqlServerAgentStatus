"""App logging setup. Exceptions go to logs/, UI shows friendly text only."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_CONFIGURED = False


def setup_logging(name: str = "sqlmonitor") -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger(name)
    if _CONFIGURED:
        return logger

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    fh = RotatingFileHandler(
        _LOG_DIR / "activity.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.setLevel(logging.WARNING)
    logger.addHandler(sh)

    _CONFIGURED = True
    return logger


def get_logger(name: str = "sqlmonitor") -> logging.Logger:
    if not _CONFIGURED:
        return setup_logging(name)
    return logging.getLogger(name)
