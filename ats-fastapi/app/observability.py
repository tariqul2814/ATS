"""Logging with the analysisId as a correlation field (Req 16) and secret redaction (Req 15.3)."""

import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

_analysis_id: ContextVar[str] = ContextVar("analysis_id", default="-")

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s [analysis=%(analysis_id)s] %(message)s"


@contextmanager
def analysis_context(analysis_id: UUID | str) -> Iterator[None]:
    """Every log record emitted inside this block carries the analysisId."""
    token = _analysis_id.set(str(analysis_id))
    try:
        yield
    finally:
        _analysis_id.reset(token)


class AnalysisIdFilter(logging.Filter):
    """Stamps each record with the current analysis id from the context, defaulting to "-"."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Attach the current analysis id to the record if it has none."""
        if not hasattr(record, "analysis_id"):
            record.analysis_id = _analysis_id.get()
        return True


class SecretRedactionFilter(logging.Filter):
    """Defence in depth: nothing logs secrets on purpose, but scrub them if one slips through."""

    def __init__(self, secrets: Sequence[str]):
        super().__init__()
        self._secrets = [s for s in secrets if s and len(s) >= 4]

    def filter(self, record: logging.LogRecord) -> bool:
        """Replace any known secret in the formatted message with [REDACTED]."""
        if not self._secrets:
            return True
        message = record.getMessage()
        redacted = message
        for secret in self._secrets:
            redacted = redacted.replace(secret, "[REDACTED]")
        if redacted != message:
            record.msg, record.args = redacted, None
        return True


def configure_logging(level: str = "INFO", secrets: Sequence[str] = ()) -> None:
    """Install the "ats" logger with the analysis-id format and the id and redaction filters."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(AnalysisIdFilter())
    handler.addFilter(SecretRedactionFilter(secrets))
    logger = logging.getLogger("ats")
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
