"""POST /analyze — dispatch intake (Req 1, 2). Validates, admits, schedules, returns 202."""

import hmac
import logging

from fastapi import APIRouter, BackgroundTasks, Header, Request
from fastapi.responses import JSONResponse

from app.config import Settings
from app.contracts.dispatch import DispatchAccepted, DispatchRequest
from app.observability import analysis_context
from app.pipeline.run import Admission, AnalysisJob

log = logging.getLogger("ats.api")
router = APIRouter()

RETRY_AFTER_SECONDS = "30"


@router.post(
    "/analyze",
    status_code=202,
    response_model=DispatchAccepted,
    responses={401: {"description": "bad dispatch token"}, 422: {"description": "invalid body"},
               503: {"description": "at capacity or shutting down"}},
)
async def analyze(
    body: DispatchRequest,
    background: BackgroundTasks,
    request: Request,
    x_dispatch_token: str | None = Header(default=None),
) -> DispatchAccepted | JSONResponse:
    """Admit a dispatch: authenticate, de-duplicate, record, schedule the run, and return 202."""
    state = request.app.state
    with analysis_context(body.analysisId):
        if not _is_dispatch_authorised(state.settings, x_dispatch_token):
            log.warning("dispatch rejected: missing or invalid X-Dispatch-Token")
            return _unauthorised_response()

        job = AnalysisJob.from_dispatch(body)
        admission = state.runner.admit(job)
        if admission is Admission.DUPLICATE:
            log.info("duplicate dispatch for an analysis already in flight; not starting another run")
            return DispatchAccepted(analysisId=body.analysisId)
        if admission is not Admission.ACCEPTED:
            log.warning("dispatch rejected: %s", admission.value)
            return _at_capacity_response(admission)

        await state.tracking.upsert_received(job.analysis_id, job.resume_file_reference, state.model)
        background.add_task(state.runner.run, job)  # runs after the 202 is sent (Req 2.1)
        log.info("dispatch accepted")
        return DispatchAccepted(analysisId=body.analysisId)


def _is_dispatch_authorised(settings: Settings, supplied_token: str | None) -> bool:
    """True if no token is configured, or the supplied header matches the configured one.

    Uses a constant-time compare so a wrong token cannot be guessed from response timing.
    """
    expected = settings.dispatch.token
    if expected is None:
        return True
    supplied = (supplied_token or "").encode()
    return hmac.compare_digest(supplied, expected.get_secret_value().encode())


def _unauthorised_response() -> JSONResponse:
    """401 for a missing or invalid dispatch token."""
    return JSONResponse({"detail": "unauthorized"}, status_code=401)


def _at_capacity_response(admission: Admission) -> JSONResponse:
    """503 with Retry-After when the service is at capacity or shutting down."""
    return JSONResponse(
        {"detail": admission.value}, status_code=503, headers={"Retry-After": RETRY_AFTER_SECONDS}
    )
