"""Port for the local record of every analysis, plus the status and record types it stores."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class TrackingStatus(StrEnum):
    """Lifecycle state of a tracked analysis: received -> processing -> completed | failed."""

    RECEIVED = "received"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        """True once the analysis has finished, either completed or failed."""
        return self in (TrackingStatus.COMPLETED, TrackingStatus.FAILED)


class CallbackOutcome(StrEnum):
    """Whether the result callback reached the orchestrator."""

    DELIVERED = "delivered"
    UNDELIVERED = "undelivered"


@dataclass
class AnalysisRecord:
    """One analysis as stored locally: its status, timestamps, inputs, and result or failure."""

    analysis_id: UUID
    status: TrackingStatus
    received_at: str
    updated_at: str
    resume_file_reference: str
    model: str
    callback_outcome: CallbackOutcome | None = None
    failure_reason: str | None = None
    result_json: str | None = None


class ITrackingRepository(Protocol):
    """Local record of every analysis (Req 21). Auxiliary: implementations must never raise —
    failures are logged and swallowed so tracking can't fail an analysis (Req 21.5)."""

    async def upsert_received(self, analysis_id: UUID, resume_file_reference: str, model: str) -> None:
        """Create or refresh the record for a newly received analysis in the RECEIVED state."""
        ...

    async def mark(
        self,
        analysis_id: UUID,
        status: TrackingStatus | None = None,
        *,
        callback_outcome: CallbackOutcome | None = None,
        failure_reason: str | None = None,
        result_json: str | None = None,
    ) -> None:
        """Update the record's status and/or its callback outcome, failure reason, or result."""
        ...

    async def get(self, analysis_id: UUID) -> AnalysisRecord | None:
        """Return the stored record for an analysis, or None if there is none."""
        ...
