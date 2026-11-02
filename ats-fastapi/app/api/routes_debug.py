"""Developer test harness (ats-debug-ui spec): synchronous per-stage inspection.

Every endpoint runs one or more existing pipeline stages INLINE and returns their output, so a
developer (or the Streamlit UI) can see what the engine produces — above all the raw LLM response.
Nothing here schedules background work, signs, or posts a callback; it is request/response only.

This router reuses the stage functions and the ports wired in app.main — it adds no analysis logic,
which is what keeps the loose coupling of the ats-fastapi pipeline intact. It is mounted only when
APP_DEBUG__ENABLED is true and is unauthenticated, so it must never run in production.
"""

import logging
import time
from typing import Annotated, Any, Self

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.contracts.result import AnalysisResult
from app.pipeline.errors import AnalysisError, ResultParseError, reason_for
from app.pipeline.extract import FileType, detect_file_type, extract_text
from app.pipeline.parse import parse_result
from app.pipeline.prepare import prepare_input
from app.pipeline.prompt import build_prompt, reformat_messages

log = logging.getLogger("ats.debug")
router = APIRouter(tags=["debug"])

# Reason code -> HTTP status for the error envelope. Anything else is a generic 422.
_STATUS_FOR_REASON = {
    "file_not_found": 404,
    "llm_unreachable": 503,
    "llm_timeout": 504,
}


def _error(exc: AnalysisError, partial: dict[str, Any] | None = None) -> JSONResponse:
    """Safe error envelope: the stage's reason code and message, no stack trace/path/secret."""
    reason = reason_for(exc)
    body: dict[str, Any] = {"ok": False, "reason": reason, "detail": str(exc)}
    if partial:
        body["partial"] = partial
    return JSONResponse(body, status_code=_STATUS_FOR_REASON.get(reason, 422))


# --- request bodies for the model-free JSON endpoints ---------------------------------------


class TextPair(BaseModel):
    """Request body carrying a CV and a job description as plain text."""

    cv_text: str
    job_description: str


class RawBody(BaseModel):
    """Request body carrying a raw model-output string to validate."""

    raw: str


# --- shared helpers -------------------------------------------------------------------------


def _missing_input_response() -> JSONResponse:
    """422 for a request that supplied neither a file upload nor a readable reference."""
    return JSONResponse(
        {"ok": False, "reason": "bad_request", "detail": "provide a file upload or a reference"},
        status_code=422,
    )


async def _read_cv(request: Request, file: UploadFile | None, reference: str | None) -> tuple[bytes, FileType] | None:
    """Read the CV from the upload or the reference; None if neither was provided."""
    if file is not None:
        file_bytes = await file.read()
        return file_bytes, detect_file_type(file_bytes)
    if reference:
        return await request.app.state.components.file_store.read(reference)
    return None


# --- ping -----------------------------------------------------------------------------------


@router.get("/ping")
async def ping(request: Request) -> dict[str, Any]:
    """Report that the debug router is mounted and which model is configured."""
    return {"debug": True, "model": request.app.state.model}


@router.get("/template")
async def template(request: Request) -> dict[str, Any]:
    """Report the prompt template the service is currently configured to use.

    Returns the active template's name and its system and user parts straight from
    app.state.template. The user part is returned UNFILLED, with the {{CV_TEXT}} and
    {{JOB_DESCRIPTION}} placeholders intact — the template, not a prompt rendered for a
    specific CV. Needs no CV or job description. Use /prompt to see a filled prompt.
    """
    tpl = request.app.state.template
    return {"ok": True, "name": tpl.name, "system": tpl.system, "user": tpl.user}


# --- per-stage inspection (no model) --------------------------------------------------------


@router.post("/extract", response_model=None)
async def extract(
    request: Request,
    file: Annotated[UploadFile | None, File()] = None,
    reference: Annotated[str | None, Form()] = None,
) -> JSONResponse | dict[str, Any]:
    """Extract text from an uploaded CV, or from a file the service can read by reference."""
    try:
        cv = await _read_cv(request, file, reference)
        if cv is None:
            return _missing_input_response()
        file_bytes, file_type = cv
        text = extract_text(file_bytes, file_type)
    except AnalysisError as exc:
        return _error(exc)
    return {"ok": True, "file_type": file_type.value, "chars": len(text), "text": text}


@router.post("/prepare", response_model=None)
async def prepare(request: Request, body: TextPair) -> JSONResponse | dict[str, Any]:
    """Normalise and truncate the CV and job description, and report what was cut."""
    try:
        prepared = prepare_input(body.cv_text, body.job_description, request.app.state.limits)
    except AnalysisError as exc:
        return _error(exc)
    return {
        "ok": True,
        "cv_text": prepared.cv_text,
        "job_description": prepared.job_description,
        "truncated": prepared.truncated,
        "cv_truncated": prepared.cv_truncated,
        "jd_truncated": prepared.jd_truncated,
        "original_chars": prepared.original_chars,
        "original_jd_chars": prepared.original_jd_chars,
    }


@router.post("/prompt", response_model=None)
async def prompt(request: Request, body: TextPair) -> JSONResponse | dict[str, Any]:
    """Build the chat messages that would be sent to the model, without calling it."""
    try:
        prepared = prepare_input(body.cv_text, body.job_description, request.app.state.limits)
    except AnalysisError as exc:
        return _error(exc)
    messages = build_prompt(prepared, request.app.state.template)
    return {"ok": True, "messages": messages, "system": messages[0]["content"], "user": messages[1]["content"]}


@router.post("/parse", response_model=None)
async def parse(body: RawBody) -> JSONResponse | dict[str, Any]:
    """Validate a raw model-output string against the result schema (paste canned/edited output)."""
    try:
        result = parse_result(body.raw)
    except ResultParseError as exc:
        return _error(exc)
    return {"ok": True, "result": result.model_dump(mode="json")}


# --- the LLM response (primary goal) --------------------------------------------------------


@router.post("/llm", response_model=None)
async def llm(request: Request, body: TextPair) -> JSONResponse | dict[str, Any]:
    """Run prepare -> prompt -> the configured LLM and return the RAW, unparsed reply.

    The reply is returned as-is even if it would not validate, so weak or malformed model output is
    visible rather than hidden behind a parse failure (Req 3.2).
    """
    try:
        prepared = prepare_input(body.cv_text, body.job_description, request.app.state.limits)
        messages = build_prompt(prepared, request.app.state.template)
        started = time.perf_counter()
        raw = await request.app.state.components.llm.complete(messages)
        elapsed = time.perf_counter() - started
    except AnalysisError as exc:
        return _error(exc)
    return {"ok": True, "raw": raw, "elapsed_seconds": round(elapsed, 3)}


# --- end-to-end synchronous scoring ---------------------------------------------------------


@router.post("/score", response_model=None)
async def score(
    request: Request,
    job_description: Annotated[str, Form()],
    file: Annotated[UploadFile | None, File()] = None,
    reference: Annotated[str | None, Form()] = None,
) -> JSONResponse | dict[str, Any]:
    """Full pipeline in-process: retrieve -> extract -> prepare -> prompt -> LLM -> parse.

    Returns the raw model reply and the validated AnalysisResult together, with per-stage timings.
    On a stage failure it returns the reason code plus whatever partial output was produced, so the
    failing step is identifiable. No background task, no callback, no HMAC (Req 4).
    """
    state = request.app.state
    timings: dict[str, float] = {}
    partial: dict[str, Any] = {}
    overall = time.perf_counter()

    def _timed(name: str) -> "_Stopwatch":
        return _Stopwatch(name, timings)

    try:
        with _timed("extract"):
            cv = await _read_cv(request, file, reference)
            if cv is None:
                return _missing_input_response()
            file_bytes, file_type = cv
            text = extract_text(file_bytes, file_type)
        partial["extracted_chars"] = len(text)

        with _timed("prepare"):
            prepared = prepare_input(text, job_description, state.limits)
        with _timed("prompt"):
            messages = build_prompt(prepared, state.template)

        with _timed("llm"):
            raw = await state.components.llm.complete(messages)
        partial["raw"] = raw

        with _timed("parse"):
            result, raw = await _parse_with_reformat(state, messages, raw, partial)
    except AnalysisError as exc:
        return _error(exc, partial)

    timings["total"] = round(time.perf_counter() - overall, 3)
    return {
        "ok": True,
        "raw": raw,
        "result": result.model_dump(mode="json"),
        "truncated": {"cv": prepared.cv_truncated, "jd": prepared.jd_truncated},
        "timings": timings,
    }


async def _parse_with_reformat(
    state: Any, messages: list[Any], raw: str, partial: dict[str, Any]
) -> tuple[AnalysisResult, str]:
    """Parse the model reply, retrying once with a reformat request; return the result and raw used."""
    try:
        return parse_result(raw), raw
    except ResultParseError as error:
        log.info("debug score: reformatting after parse failure (%s)", error)
        raw = await state.components.llm.complete(reformat_messages(messages, raw, str(error)))
        partial["raw"] = raw
        return parse_result(raw), raw


class _Stopwatch:
    """Records perf_counter elapsed for a stage into a shared dict."""

    def __init__(self, name: str, into: dict[str, float]):
        self._name = name
        self._into = into

    def __enter__(self) -> Self:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        self._into[self._name] = round(time.perf_counter() - self._start, 3)
