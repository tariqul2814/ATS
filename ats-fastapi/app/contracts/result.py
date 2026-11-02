"""The analysis result document (Req 8, resolved Q3). Stored opaquely by the orchestrator."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Rubric maxima (Req 6.5). Order is the order categories appear in the breakdown.
RUBRIC: dict[str, int] = {
    "keyword_match": 35,
    "experience_relevance": 25,
    "achievements_impact": 15,
    "ats_formatting": 15,
    "education_certifications": 10,
}

Category = Literal[
    "keyword_match",
    "experience_relevance",
    "achievements_impact",
    "ats_formatting",
    "education_certifications",
]


class Band(StrEnum):
    """The qualitative label for an overall score, from Strong down to Weak."""

    STRONG = "Strong"
    GOOD = "Good"
    MODERATE = "Moderate"
    WEAK = "Weak"

    @classmethod
    def for_score(cls, score: int) -> "Band":
        """Return the band a 0-100 score falls into."""
        if score >= 80:
            return cls.STRONG
        if score >= 65:
            return cls.GOOD
        if score >= 50:
            return cls.MODERATE
        return cls.WEAK


class Requirement(StrEnum):
    """Whether a job-description keyword is required or merely preferred."""

    REQUIRED = "required"
    PREFERRED = "preferred"


class CategoryScore(BaseModel):
    """One rubric category's score, capped at that category's maximum, with the reasoning."""

    category: Category
    score: int = Field(ge=0)
    max: int
    reason: str

    @model_validator(mode="after")
    def _within_rubric(self) -> "CategoryScore":
        if self.max != RUBRIC[self.category]:
            raise ValueError(f"{self.category} max must be {RUBRIC[self.category]}")
        if self.score > self.max:
            raise ValueError(f"{self.category} score {self.score} exceeds max {self.max}")
        return self


class MissingKeyword(BaseModel):
    """A job-description keyword absent from the CV, flagged as a skill gap or placed to add."""

    keyword: str
    requirement: Requirement
    whereToAdd: str | None = None
    skillGap: bool = False

    @model_validator(mode="after")
    def _gap_xor_where(self) -> "MissingKeyword":
        if self.skillGap:
            self.whereToAdd = None
        elif not self.whereToAdd:
            # No guidance on where to add it means the CV shows no basis for it (Req 20.3).
            self.skillGap = True
        return self


class Improvement(BaseModel):
    """A suggested CV edit: the section, the problem, the original text, and the rewrite."""

    section: str
    problem: str
    original: str
    suggested: str


class AnalysisResult(BaseModel):
    """The full scored assessment of one CV against one job description."""

    score: int = Field(ge=0, le=100)
    band: Band
    breakdown: list[CategoryScore]
    summary: str
    matchedKeywords: list[str]
    missingKeywords: list[MissingKeyword]
    formattingIssues: list[str]
    topImprovements: list[Improvement]
    strengths: list[str]
    revisedSummary: str
    reportMarkdown: str

    @model_validator(mode="after")
    def _complete_breakdown(self) -> "AnalysisResult":
        categories = [c.category for c in self.breakdown]
        if sorted(categories) != sorted(RUBRIC):
            raise ValueError("breakdown must contain each rubric category exactly once")
        return self


# Fields the service fills in itself rather than asking the model for. reportMarkdown is rendered
# from the validated structured fields: it is deterministic and saves ~30% of generated tokens.
SERVICE_RENDERED_FIELDS = ("reportMarkdown",)

MAX_IMPROVEMENTS = 5

# Size caps on the model's reply, enforced by the output grammar. Without them the reply length is
# open-ended: the same prompt produced 982 tokens on one run and 2,800+ unfinished at the timeout on
# another. At the caps a reply is ~2,750 tokens, which fits the LLM timeout on the measured CPU host.
# The grammar cuts text off mid-word at a cap, so these sit above real output and the prompt asks for
# the same limits. They apply to the model's reply only, not to AnalysisResult.
_MAX_ITEMS = {
    "breakdown": len(RUBRIC),
    "matchedKeywords": 15,
    "missingKeywords": 10,
    "formattingIssues": 5,
    "topImprovements": MAX_IMPROVEMENTS,
    "strengths": 5,
}
_MAX_CHARS = {
    "reason": 200,
    "summary": 400,
    "revisedSummary": 500,
    "matchedKeywords": 40,
    "keyword": 40,
    "whereToAdd": 80,
    "formattingIssues": 150,
    "strengths": 150,
    "section": 40,
    "problem": 120,
    "original": 300,
    "suggested": 300,
}


def _cap_text(spec: dict, limit: int) -> None:
    for option in spec.get("anyOf", [spec]):
        if option.get("type") == "string":
            option["maxLength"] = limit


def _apply_size_caps(schema: dict) -> None:
    for definition in (schema, *schema.get("$defs", {}).values()):
        for name, prop in definition.get("properties", {}).items():
            if name in _MAX_ITEMS:
                prop["maxItems"] = _MAX_ITEMS[name]
            if name in _MAX_CHARS:
                _cap_text(prop.get("items", prop), _MAX_CHARS[name])


def model_output_schema() -> dict:
    """JSON schema the LLM's reply must follow: the result minus service-rendered fields, size-capped."""
    schema = AnalysisResult.model_json_schema()
    for name in SERVICE_RENDERED_FIELDS:
        schema["properties"].pop(name, None)
        schema["required"] = [f for f in schema.get("required", []) if f != name]
    _apply_size_caps(schema)
    return schema
