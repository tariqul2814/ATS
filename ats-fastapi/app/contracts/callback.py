"""Callback posted to the orchestrator (Req 9, 11; ats-backend `AnalysisResultCallback`)."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, model_validator

from app.contracts.result import AnalysisResult


class CallbackStatus(StrEnum):
    """Terminal outcome reported to the orchestrator: the analysis completed or failed."""

    COMPLETED = "Completed"
    FAILED = "Failed"


class AnalysisResultCallback(BaseModel):
    """The webhook body: a completed callback carries a result, a failed one carries an error."""

    analysisId: UUID
    status: CallbackStatus
    result: AnalysisResult | None = None
    error: str | None = None

    @model_validator(mode="after")
    def _envelope(self) -> "AnalysisResultCallback":
        if self.status is CallbackStatus.COMPLETED and (self.result is None or self.error is not None):
            raise ValueError("Completed callback needs a result and no error")
        if self.status is CallbackStatus.FAILED and (self.result is not None or not self.error):
            raise ValueError("Failed callback needs an error and no result")
        return self

    @classmethod
    def completed(cls, analysis_id: UUID, result: AnalysisResult) -> "AnalysisResultCallback":
        """Build a Completed callback carrying the scored result."""
        return cls(analysisId=analysis_id, status=CallbackStatus.COMPLETED, result=result)

    @classmethod
    def failed(cls, analysis_id: UUID, reason: str) -> "AnalysisResultCallback":
        """Build a Failed callback carrying the safe failure reason code."""
        return cls(analysisId=analysis_id, status=CallbackStatus.FAILED, error=reason)

    def to_body(self) -> bytes:
        """Serialize once; these exact bytes are signed and sent (Req 10.4)."""
        return self.model_dump_json().encode("utf-8")
