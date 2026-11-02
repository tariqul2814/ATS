"""Stage failures. Each carries the safe reason code sent in the Failed callback (Req 11.3)."""


class AnalysisError(Exception):
    """Base for any failure that ends an analysis; `reason` is the fallback for unmapped errors."""

    reason = "unexpected_error"


class FileRetrievalError(AnalysisError):
    """The CV file could not be found or read from the store."""

    reason = "file_not_found"


class ExtractionEmptyError(AnalysisError):
    """Text extraction succeeded but produced no usable content (e.g. a blank or scanned PDF)."""

    reason = "extraction_empty"


class ExtractionError(AnalysisError):
    """The file could not be parsed as its declared type (corrupt or unsupported content)."""

    reason = "extraction_failed"


class InputTooLargeError(AnalysisError):
    """The CV or job description exceeds the hard character ceiling, past any truncation."""

    reason = "input_too_large"


class LlmUnavailableError(AnalysisError):
    """The model backend is unreachable, errored, or lacks the configured model."""

    reason = "llm_unreachable"


class LlmTimeoutError(AnalysisError):
    """The model did not reply within the configured timeout, or the analysis budget ran out."""

    reason = "llm_timeout"


class ResultParseError(AnalysisError):
    """The model's reply could not be parsed into a valid result, even after one reformat retry."""

    reason = "result_unparseable"


class CallbackTransportError(Exception):
    """Connection error or timeout while posting a callback (transient, Req 12.1)."""


def reason_for(exc: BaseException) -> str:
    """Map an exception to its safe reason code, falling back to "unexpected_error"."""
    return exc.reason if isinstance(exc, AnalysisError) else AnalysisError.reason
