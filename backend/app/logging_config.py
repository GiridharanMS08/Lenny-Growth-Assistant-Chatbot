
import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import PROJECT_DIR

LOG_DIR = PROJECT_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_SECRET_PATTERNS = (
    re.compile(r"(?i)(password|passwd|pwd)\s*=\s*[^&\s]+"),
    re.compile(r"(?i)(password|passwd|pwd)\s*:\s*[^,\s]+"),
    re.compile(r"(?i)(api[_-]?key|token|secret)\s*=\s*[^&\s]+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]+"),
    re.compile(r"(?i)(postgresql(?:\+\w+)?://)([^:\s/]+):([^@\s]+)@"),
)


def sanitize_log_value(value: object) -> str:
    text = str(value)
    for pattern in _SECRET_PATTERNS:
        if "postgresql" in pattern.pattern.lower():
            text = pattern.sub(r"\1***:***@", text)
        elif "bearer" in pattern.pattern.lower():
            text = pattern.sub("Bearer ***", text)
        else:
            text = pattern.sub(lambda m: f"{m.group(1)}=***", text)
    return text.replace("\n", "\\n").replace("\r", "\\r")[:2000]


def get_file_logger(name: str, filename: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        handler = RotatingFileHandler(
            LOG_DIR / filename,
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(message)s",
                "%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)

    return logger


backend_logger = get_file_logger("lenny.backend", "backend.logs")
db_logger = get_file_logger("lenny.db", "db.logs")
frontend_logger = get_file_logger("lenny.frontend", "frontend.logs")
