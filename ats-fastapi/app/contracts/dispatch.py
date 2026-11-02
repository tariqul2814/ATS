"""Dispatch request received from the orchestrator (Req 1; ats-backend "External contract: dispatch")."""

from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator


class DispatchRequest(BaseModel):
    """The work handed over by the orchestrator: which CV, which job description, where to call back."""

    analysisId: UUID
    resumeFileReference: str = Field(min_length=1)
    jobDescription: str
    callbackUrl: AnyHttpUrl

    @field_validator("resumeFileReference", "jobDescription")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty or whitespace")
        return value


class DispatchAccepted(BaseModel):
    """The 202 acknowledgement: the analysis id and a fixed "accepted" status."""

    analysisId: UUID
    status: str = "accepted"
