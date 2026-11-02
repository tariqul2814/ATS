"""Pipeline orchestration (Req 2.2, 11). The only place the stages are wired together.

Guarantees exactly one terminal callback per accepted analysis: whatever happens while scoring,
run_analysis ends by delivering either Completed or Failed (Req 2.4, 11.4).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

import anyio

from app.contracts.callback import AnalysisResultCallback
from app.contracts.dispatch import DispatchRequest
from app.contracts.result import AnalysisResult
from app.observability import analysis_context
from app.pipeline.deliver import CallbackDelivery
from app.pipeline.errors import LlmTimeoutError, ResultParseError, reason_for
from app.pipeline.extract import extract_text
from app.pipeline.parse import parse_result
from app.pipeline.prepare import InputLimits, prepare_input
from app.pipeline.prompt import ChatMessage, PromptTemplate, build_prompt, reformat_messages
from app.ports.file_store import IFileStore
from app.ports.llm_client import ILlmClient
from app.ports.tracking_repo import CallbackOutcome, ITrackingRepository, TrackingStatus

log = logging.getLogger("ats.pipeline")


@dataclass(frozen=True)
class AnalysisJob:
    """One unit of scoring work: the CV reference, the job description, and the callback URL."""

    analysis_id: UUID
    resume_file_reference: str
    job_description: str
    callback_url: str

    @classmethod
    def from_dispatch(cls, request: DispatchRequest) -> "AnalysisJob":
        """Build an AnalysisJob from the dispatch request received from the orchestrator."""
        return cls(
            request.analysisId, request.resumeFileReference, request.jobDescription, str(request.callbackUrl)
        )


@dataclass
class PipelineDeps:
    """The collaborators and limits a pipeline run needs, assembled once at startup."""

    file_store: IFileStore
    llm: ILlmClient
    delivery: CallbackDelivery
    tracking: ITrackingRepository
    template: PromptTemplate
    limits: InputLimits
    llm_semaphore: asyncio.Semaphore
    # Seconds an analysis may spend queued + scoring before it is failed so its callback still
    # beats the orchestrator's timeout sweeper (see Settings.analysis_budget_seconds).
    budget_seconds: float


async def run_analysis(job: AnalysisJob, pipeline_deps: PipelineDeps) -> CallbackOutcome:
    """Run one analysis end to end and deliver exactly one terminal callback.

    Scores under the time budget, records the outcome, then delivers the Completed or Failed
    callback. On shutdown the scoring is cancelled and left for the orchestrator's sweeper, so no
    callback is sent (Req 2.4, 11.4).
    """
    with analysis_context(job.analysis_id):
        try:
            callback = await _score_and_record_outcome(job, pipeline_deps)
        except asyncio.CancelledError:
            log.warning("analysis cancelled (service shutting down); orchestrator sweeper will fail it")
            raise
        return await _deliver_callback(job, pipeline_deps, callback)


async def _score_and_record_outcome(job: AnalysisJob, pipeline_deps: PipelineDeps) -> AnalysisResultCallback:
    """Score within the budget and persist the outcome; return the callback to deliver."""
    loop = asyncio.get_running_loop()
    started = loop.time()
    try:
        async with asyncio.timeout(pipeline_deps.budget_seconds):
            result = await _score(job, pipeline_deps)
    except Exception as error:  # noqa: BLE001 — any scoring failure becomes a Failed callback
        return await _record_failure(job, pipeline_deps, error)
    return await _record_success(job, pipeline_deps, result, loop.time() - started)


async def _record_success(
    job: AnalysisJob, pipeline_deps: PipelineDeps, result: AnalysisResult, elapsed_seconds: float
) -> AnalysisResultCallback:
    """Log and persist a completed analysis, and return its Completed callback."""
    log.info("analysis completed: score %d (%s) in %.1fs", result.score, result.band, elapsed_seconds)
    await pipeline_deps.tracking.mark(
        job.analysis_id, TrackingStatus.COMPLETED, result_json=result.model_dump_json()
    )
    return AnalysisResultCallback.completed(job.analysis_id, result)


async def _record_failure(
    job: AnalysisJob, pipeline_deps: PipelineDeps, error: Exception
) -> AnalysisResultCallback:
    """Map the error to a safe reason, log and persist the failure, and return its Failed callback."""
    if isinstance(error, TimeoutError):  # the overall budget ran out
        error = LlmTimeoutError(f"analysis exceeded its {pipeline_deps.budget_seconds:.0f}s budget")
    reason = reason_for(error)
    if reason == "unexpected_error":
        log.exception("analysis failed unexpectedly")
    else:
        log.warning("analysis failed: %s (%s)", reason, error)
    await pipeline_deps.tracking.mark(job.analysis_id, TrackingStatus.FAILED, failure_reason=reason)
    return AnalysisResultCallback.failed(job.analysis_id, reason)


async def _deliver_callback(
    job: AnalysisJob, pipeline_deps: PipelineDeps, callback: AnalysisResultCallback
) -> CallbackOutcome:
    """Deliver the callback and record whether it reached the orchestrator."""
    try:
        outcome = await pipeline_deps.delivery.deliver(job.callback_url, callback)
    except Exception:  # delivery must never crash the run; record it as undelivered
        log.exception("callback delivery crashed")
        outcome = CallbackOutcome.UNDELIVERED
    await pipeline_deps.tracking.mark(job.analysis_id, callback_outcome=outcome)
    return outcome


async def _score(job: AnalysisJob, pipeline_deps: PipelineDeps) -> AnalysisResult:
    """Score the CV against the job description: retrieve, extract, prompt, call the model, parse."""
    await pipeline_deps.tracking.mark(job.analysis_id, TrackingStatus.PROCESSING)
    cv_text = await _load_cv_text(job, pipeline_deps)
    messages = _build_scoring_prompt(job, pipeline_deps, cv_text)
    return await _ask_model(pipeline_deps, messages)


async def _load_cv_text(job: AnalysisJob, pipeline_deps: PipelineDeps) -> str:
    """Retrieve the CV and extract its text, parsing off the event loop (CPU-bound)."""
    file_bytes, file_type = await pipeline_deps.file_store.read(job.resume_file_reference)
    log.info("file retrieved: %s, %d bytes", file_type.value, len(file_bytes))
    cv_text = await anyio.to_thread.run_sync(extract_text, file_bytes, file_type)
    log.info("text extracted: %d chars", len(cv_text))
    return cv_text


def _build_scoring_prompt(job: AnalysisJob, pipeline_deps: PipelineDeps, cv_text: str) -> list[ChatMessage]:
    """Prepare the inputs within budget and render the prompt messages."""
    prepared = prepare_input(cv_text, job.job_description, pipeline_deps.limits)
    if prepared.truncated:
        log.info(
            "input truncated to budget: CV %d->%d chars, JD %d->%d chars",
            prepared.original_chars,
            len(prepared.cv_text),
            prepared.original_jd_chars,
            len(prepared.job_description),
        )
    return build_prompt(prepared, pipeline_deps.template)


async def _ask_model(pipeline_deps: PipelineDeps, messages: list[ChatMessage]) -> AnalysisResult:
    """Call the model under the concurrency semaphore and parse its reply into a result."""
    if pipeline_deps.llm_semaphore.locked():
        log.info("waiting for an LLM slot")
    # One slot per model call: a slow CPU host can't run more generations than it has cores for.
    async with pipeline_deps.llm_semaphore:
        log.info("LLM invoked: %s", pipeline_deps.llm.model)
        raw_model_output = await pipeline_deps.llm.complete(messages)
        log.info("LLM returned %d chars", len(raw_model_output))
        result = await _parse_or_reformat(pipeline_deps, messages, raw_model_output)
    log.info("result parsed")
    return result


async def _parse_or_reformat(
    pipeline_deps: PipelineDeps, messages: list[ChatMessage], raw_model_output: str
) -> AnalysisResult:
    """Parse the model reply, giving the model one chance to fix malformed output before failing."""
    try:
        return parse_result(raw_model_output)
    except ResultParseError as error:
        log.warning("model output unusable (%s); asking for a reformat", error)
        reformatted = await pipeline_deps.llm.complete(reformat_messages(messages, raw_model_output, str(error)))
        log.info("LLM returned %d chars (reformat)", len(reformatted))
        return parse_result(reformatted)


class Admission(StrEnum):
    """Outcome of admission control for a dispatch: accepted, or why it was turned away."""

    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    AT_CAPACITY = "at_capacity"
    SHUTTING_DOWN = "shutting_down"


@dataclass
class AnalysisRunner:
    """Admission control for background analyses: capacity cap (Req 2.5) and de-duplication of
    analyses already in flight (Req 17.1)."""

    deps: PipelineDeps
    max_in_flight: int
    in_flight: set[UUID] = field(default_factory=set)
    accepting: bool = True

    def admit(self, job: AnalysisJob) -> Admission:
        """Claim an in-flight slot for the job, or return why it cannot be admitted.

        A slot claimed here is released by `run`'s finally block once the analysis finishes.
        """
        if not self.accepting:
            return Admission.SHUTTING_DOWN
        if job.analysis_id in self.in_flight:
            return Admission.DUPLICATE
        if len(self.in_flight) >= self.max_in_flight:
            return Admission.AT_CAPACITY
        self.in_flight.add(job.analysis_id)
        return Admission.ACCEPTED

    async def run(self, job: AnalysisJob) -> CallbackOutcome:
        """Run the analysis, always releasing the job's in-flight slot when it finishes."""
        try:
            return await run_analysis(job, self.deps)
        finally:
            self.in_flight.discard(job.analysis_id)
