"""Logs correlate by analysisId and never carry secrets or CV/JD content (Req 15.3, 16)."""

import logging
import uuid

import pytest

from app.observability import AnalysisIdFilter, SecretRedactionFilter, analysis_context, configure_logging
from app.pipeline.errors import (
    AnalysisError,
    ExtractionEmptyError,
    ExtractionError,
    FileRetrievalError,
    InputTooLargeError,
    LlmTimeoutError,
    LlmUnavailableError,
    ResultParseError,
    reason_for,
)
from tests.unit.test_run import VALID, World


class Capture(logging.Handler):
    def __init__(self, *filters):
        super().__init__()
        self.records: list[logging.LogRecord] = []
        for f in filters:
            self.addFilter(f)

    def emit(self, record):
        self.records.append(record)

    @property
    def text(self) -> str:
        return "\n".join(self.format(r) for r in self.records)


@pytest.fixture
def capture():
    handler = Capture(AnalysisIdFilter(), SecretRedactionFilter(["test-secret-value"]))
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s [%(analysis_id)s] %(message)s"))
    logger = logging.getLogger("ats")
    old_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield handler
    logger.removeHandler(handler)
    logger.setLevel(old_level)


def test_context_binds_and_resets(capture):
    log = logging.getLogger("ats.test")
    aid = uuid.uuid4()
    with analysis_context(aid):
        log.info("inside")
    log.info("outside")
    assert [r.analysis_id for r in capture.records] == [str(aid), "-"]


def test_secret_is_redacted(capture):
    logging.getLogger("ats.test").warning("oops %s leaked", "test-secret-value")
    assert "test-secret-value" not in capture.text
    assert "[REDACTED]" in capture.text


async def test_full_run_logs_no_cv_jd_or_secret(capture):
    world = World(VALID)
    await world.run()
    text = capture.text
    assert "callback delivered" in text
    # Distinctive CV and JD content never reaches the logs, nor do signatures or the secret.
    for sensitive in ("Alex Example", "alex@example.com", "2M requests/day", "Senior Backend Engineer",
                      "secret", "X-Signature"):
        assert sensitive not in text, sensitive
    for _, _, headers in world.callbacks.posts:
        assert headers["X-Signature"] not in text


async def test_failure_logs_reason_without_internals(capture):
    world = World(file_error=FileRetrievalError(r"resume file not found"))
    await world.run()
    assert "analysis failed: file_not_found" in capture.text
    assert "Traceback" not in capture.text  # expected failures are not logged as crashes


@pytest.mark.parametrize(
    "exc,reason",
    [
        (FileRetrievalError("x"), "file_not_found"),
        (ExtractionEmptyError("x"), "extraction_empty"),
        (ExtractionError("x"), "extraction_failed"),
        (InputTooLargeError("x"), "input_too_large"),
        (LlmUnavailableError("x"), "llm_unreachable"),
        (LlmTimeoutError("x"), "llm_timeout"),
        (ResultParseError("x"), "result_unparseable"),
        (AnalysisError("x"), "unexpected_error"),
        (KeyError(r"C:\secret\path"), "unexpected_error"),
    ],
)
def test_reason_codes_are_fixed_and_safe(exc, reason):
    assert reason_for(exc) == reason  # the callback carries only this code, never str(exc)


def test_configure_logging_installs_filters():
    configure_logging("INFO", secrets=["abcd-secret"])
    logger = logging.getLogger("ats")
    try:
        [handler] = logger.handlers
        assert any(isinstance(f, AnalysisIdFilter) for f in handler.filters)
        assert any(isinstance(f, SecretRedactionFilter) for f in handler.filters)
        assert logger.propagate is False
    finally:
        logger.handlers = []
        logger.propagate = True
        logger.setLevel(logging.NOTSET)
