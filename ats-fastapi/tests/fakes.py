"""In-memory fakes for every port (Req 22.6). They satisfy the Protocols structurally."""

from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

from app.pipeline.errors import CallbackTransportError
from app.pipeline.extract import FileType
from app.pipeline.prompt import ChatMessage
from app.ports.callback_client import CallbackResponse
from app.ports.tracking_repo import AnalysisRecord, CallbackOutcome, TrackingStatus


class FakeFileStore:
    def __init__(
        self,
        files: dict[str, tuple[bytes, FileType]] | None = None,
        error: Exception | None = None,
        ready: bool = True,
    ):
        self.files = files or {}
        self.error = error
        self.ready = ready
        self.reads: list[str] = []

    async def read(self, reference: str) -> tuple[bytes, FileType]:
        self.reads.append(reference)
        if self.error:
            raise self.error
        return self.files[reference]

    async def check_ready(self) -> bool:
        return self.ready


class FakeLlmClient:
    """Returns queued replies in order; a queued exception is raised instead."""

    model = "fake-model"

    def __init__(self, *replies: str | Exception, ready: bool = True):
        self.replies = list(replies)
        self.calls: list[list[ChatMessage]] = []
        self.ready = ready

    async def complete(self, messages: list[ChatMessage], *, json_mode: bool = True) -> str:
        self.calls.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    async def check_ready(self) -> bool:
        return self.ready


class FakeCallbackClient:
    """Answers with queued status codes (or raises queued exceptions); repeats the last one."""

    def __init__(self, *responses: int | Exception):
        self.responses = list(responses) or [200]
        self.posts: list[tuple[str, bytes, dict[str, str]]] = []

    async def post(self, url: str, body: bytes, headers: Mapping[str, str]) -> CallbackResponse:
        self.posts.append((url, body, dict(headers)))
        reply = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(reply, Exception):
            raise reply
        return CallbackResponse(reply)


class FakeTrackingRepository:
    def __init__(self, fail: bool = False):
        self.records: dict[UUID, AnalysisRecord] = {}
        self.history: list[tuple[UUID, TrackingStatus | None]] = []
        self.fail = fail

    async def upsert_received(self, analysis_id: UUID, resume_file_reference: str, model: str) -> None:
        if self.fail:
            return  # real implementation logs and swallows
        now = datetime.now(UTC).isoformat()
        self.records[analysis_id] = AnalysisRecord(
            analysis_id, TrackingStatus.RECEIVED, now, now, resume_file_reference, model
        )
        self.history.append((analysis_id, TrackingStatus.RECEIVED))

    async def mark(
        self,
        analysis_id: UUID,
        status: TrackingStatus | None = None,
        *,
        callback_outcome: CallbackOutcome | None = None,
        failure_reason: str | None = None,
        result_json: str | None = None,
    ) -> None:
        if self.fail or analysis_id not in self.records:
            return
        rec = self.records[analysis_id]
        if status:
            rec.status = status
        if callback_outcome:
            rec.callback_outcome = callback_outcome
        if failure_reason:
            rec.failure_reason = failure_reason
        if result_json:
            rec.result_json = result_json
        self.history.append((analysis_id, status))

    async def get(self, analysis_id: UUID) -> AnalysisRecord | None:
        return None if self.fail else self.records.get(analysis_id)


def transport_error() -> CallbackTransportError:
    return CallbackTransportError("connection refused")
