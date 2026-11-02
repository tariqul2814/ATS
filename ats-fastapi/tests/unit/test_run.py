"""run_analysis end-to-end with fakes: one terminal callback per analysis, always (Req 2.4, 11, 22.3)."""

import asyncio
import json
import logging
import uuid

import pytest

from app.observability import AnalysisIdFilter
from app.pipeline.deliver import CallbackDelivery, RetryPolicy
from app.pipeline.errors import FileRetrievalError, LlmTimeoutError, LlmUnavailableError
from app.pipeline.extract import FileType
from app.pipeline.prepare import InputLimits
from app.pipeline.prompt import load_template
from app.pipeline.run import Admission, AnalysisJob, AnalysisRunner, PipelineDeps, run_analysis
from app.ports.tracking_repo import CallbackOutcome, TrackingStatus
from tests.conftest import ASSETS
from tests.fakes import FakeCallbackClient, FakeFileStore, FakeLlmClient, FakeTrackingRepository

REF = r"C:\ats\storage\cv.pdf"
URL = "https://ats.test/api/webhooks/analysis-completed"
VALID = (ASSETS / "model_output_valid.json").read_text()
MALFORMED = (ASSETS / "model_output_malformed.txt").read_text()
PDF = (ASSETS / "sample_cv.pdf").read_bytes()


def job() -> AnalysisJob:
    return AnalysisJob(uuid.uuid4(), REF, (ASSETS / "sample_jd.txt").read_text(), URL)


class World:
    def __init__(self, *llm_replies, files=None, file_error=None, callbacks=(200,), limits=None, budget=60.0):
        self.files = FakeFileStore(files if files is not None else {REF: (PDF, FileType.PDF)}, error=file_error)
        self.llm = FakeLlmClient(*(llm_replies or (VALID,)))
        self.callbacks = FakeCallbackClient(*callbacks)
        self.tracking = FakeTrackingRepository()

        async def no_sleep(_):
            pass

        self.deps = PipelineDeps(
            file_store=self.files,
            llm=self.llm,
            delivery=CallbackDelivery(self.callbacks, "secret", RetryPolicy(retry_count=2), sleep=no_sleep),
            tracking=self.tracking,
            template=load_template("ats_rubric_v1"),
            limits=limits or InputLimits(24000, 8000, 120000),
            llm_semaphore=asyncio.Semaphore(2),
            budget_seconds=budget,
        )

    async def run(self, j=None):
        j = j or job()
        await self.tracking.upsert_received(j.analysis_id, j.resume_file_reference, "fake-model")
        outcome = await run_analysis(j, self.deps)
        return j, outcome

    def bodies(self) -> list[dict]:
        return [json.loads(body) for _, body, _ in self.callbacks.posts]


def assert_single_failed(world: World, reason: str):
    bodies = world.bodies()
    assert len(bodies) == 1, "exactly one callback"
    assert bodies[0]["status"] == "Failed"
    assert bodies[0]["error"] == reason
    assert bodies[0]["result"] is None


async def test_happy_path_one_completed_callback():
    w = World(VALID)
    j, outcome = await w.run()
    assert outcome is CallbackOutcome.DELIVERED
    [body] = w.bodies()
    assert body["status"] == "Completed" and body["error"] is None
    assert body["analysisId"] == str(j.analysis_id)
    assert body["result"]["score"] == 72
    rec = w.tracking.records[j.analysis_id]
    assert rec.status is TrackingStatus.COMPLETED
    assert rec.callback_outcome is CallbackOutcome.DELIVERED
    assert json.loads(rec.result_json)["score"] == 72
    statuses = [s for _, s in w.tracking.history if s]
    assert statuses == [TrackingStatus.RECEIVED, TrackingStatus.PROCESSING, TrackingStatus.COMPLETED]


async def test_prompt_contains_cv_and_jd():
    w = World(VALID)
    await w.run()
    user = w.llm.calls[0][1]["content"]
    assert "Alex Example" in user and "Senior Backend Engineer" in user


@pytest.mark.parametrize(
    "setup,reason",
    [
        ({"file_error": FileRetrievalError("gone")}, "file_not_found"),
        ({"files": {REF: ((ASSETS / "blank.pdf").read_bytes(), FileType.PDF)}}, "extraction_empty"),
        ({"files": {REF: (b"%PDF-1.7 broken", FileType.PDF)}}, "extraction_failed"),
        ({"limits": InputLimits(100, 100, 200)}, "input_too_large"),
        ({"llm": (LlmUnavailableError("down"),)}, "llm_unreachable"),
        ({"llm": (LlmTimeoutError("slow"),)}, "llm_timeout"),
        ({"llm": (MALFORMED, MALFORMED)}, "result_unparseable"),
        ({"llm": (RuntimeError("bug in a stage"),)}, "unexpected_error"),
    ],
)
async def test_each_stage_failure_gives_one_failed_callback(setup, reason):
    w = World(*setup.pop("llm", ()), **setup)
    j, outcome = await w.run()
    assert outcome is CallbackOutcome.DELIVERED
    assert_single_failed(w, reason)
    rec = w.tracking.records[j.analysis_id]
    assert rec.status is TrackingStatus.FAILED and rec.failure_reason == reason


async def test_reformat_retry_recovers():
    w = World(MALFORMED, VALID)
    await w.run()
    assert len(w.llm.calls) == 2
    assert w.llm.calls[1][-1]["role"] == "user" and "ONLY the single JSON object" in w.llm.calls[1][-1]["content"]
    assert w.bodies()[0]["status"] == "Completed"


async def test_budget_exhaustion_fails_in_time():
    w = World(budget=0.05)

    async def stuck(messages, *, json_mode=True):
        await asyncio.sleep(10)

    w.llm.complete = stuck
    await asyncio.wait_for(w.run(), timeout=2)
    assert_single_failed(w, "llm_timeout")


async def test_undelivered_callback_recorded():
    w = World(VALID, callbacks=(503,))
    j, outcome = await w.run()
    assert outcome is CallbackOutcome.UNDELIVERED
    assert len(w.callbacks.posts) == 3  # 1 + 2 retries
    assert w.tracking.records[j.analysis_id].callback_outcome is CallbackOutcome.UNDELIVERED


async def test_tracking_outage_does_not_affect_analysis():
    w = World(VALID)
    w.tracking.fail = True
    _, outcome = await w.run()
    assert outcome is CallbackOutcome.DELIVERED
    assert w.bodies()[0]["status"] == "Completed"


async def test_crash_in_delivery_does_not_escape():
    w = World(VALID)

    async def boom(url, callback):
        raise RuntimeError("delivery bug")

    w.deps.delivery.deliver = boom
    _, outcome = await w.run()
    assert outcome is CallbackOutcome.UNDELIVERED


async def test_every_pipeline_log_carries_the_analysis_id():
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = Capture()
    handler.addFilter(AnalysisIdFilter())
    logger = logging.getLogger("ats")
    logger.addHandler(handler)
    logger.setLevel("INFO")
    try:
        j, _ = await World(VALID).run()
    finally:
        logger.removeHandler(handler)
    events = [r.getMessage() for r in records]
    for expected in ("file retrieved", "text extracted", "LLM invoked", "LLM returned", "result parsed",
                     "callback delivered"):
        assert any(e.startswith(expected) for e in events), expected
    assert {r.analysis_id for r in records} == {str(j.analysis_id)}


async def test_semaphore_bounds_concurrent_llm_calls():
    w = World(*([VALID] * 5))
    w.deps.llm_semaphore = asyncio.Semaphore(2)
    active = peak = 0
    original = w.llm.complete

    async def tracked(messages, *, json_mode=True):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return await original(messages, json_mode=json_mode)

    w.llm.complete = tracked
    await asyncio.gather(*(w.run() for _ in range(5)))
    assert peak == 2
    assert all(b["status"] == "Completed" for b in w.bodies())


def test_runner_admission_rules():
    runner = AnalysisRunner(deps=World().deps, max_in_flight=2)
    a, b, c = job(), job(), job()
    assert runner.admit(a) is Admission.ACCEPTED
    assert runner.admit(a) is Admission.DUPLICATE
    assert runner.admit(b) is Admission.ACCEPTED
    assert runner.admit(c) is Admission.AT_CAPACITY
    runner.accepting = False
    assert runner.admit(c) is Admission.SHUTTING_DOWN


async def test_runner_releases_slot_when_done():
    w = World(VALID)
    runner = AnalysisRunner(deps=w.deps, max_in_flight=1)
    j = job()
    assert runner.admit(j) is Admission.ACCEPTED
    await runner.run(j)
    assert j.analysis_id not in runner.in_flight
    assert runner.admit(job()) is Admission.ACCEPTED
