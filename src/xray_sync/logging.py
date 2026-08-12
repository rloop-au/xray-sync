from __future__ import annotations

import logging
import re
from typing import Final

from rich.logging import RichHandler

SECRET_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"(authorization:\s*bearer\s+)[^\s]+", re.IGNORECASE),
    re.compile(r"(authorization:\s*basic\s+)[^\s]+", re.IGNORECASE),
    re.compile(r"(x-access-token[\"'`:\s,()b]+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"(client_secret[\"'=:\s]+)[^\"'\s,}]+", re.IGNORECASE),
    re.compile(r"(token[\"'=:\s]+)[^\"'\s,}]+", re.IGNORECASE),
)


def redact(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(r"\1<redacted>", redacted)
    return redacted


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        if record.args:
            record.args = tuple(redact(str(arg)) for arg in record.args)
        return True


def configure_logging(*, verbose: bool = False, debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=debug, markup=False)],
        force=True,
    )
    logging.getLogger().addFilter(RedactingFilter())
