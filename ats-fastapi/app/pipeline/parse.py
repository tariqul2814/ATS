"""Result parsing and validation (Req 8). Pure: raw model text in, validated AnalysisResult out.

Repairs what can be repaired without inventing content (fences, numeric strings, out-of-range scores,
inconsistent totals/band, repeated list items, "no issues" filler, no-op improvements) and raises
ResultParseError for anything structural. reportMarkdown is always rendered here from the validated
fields; the model is not asked for it.
"""

import json
import re
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from app.contracts.result import MAX_IMPROVEMENTS, RUBRIC, AnalysisResult, Band
from app.pipeline.errors import ResultParseError

_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")
_LIST_FIELDS = ("matchedKeywords", "missingKeywords", "formattingIssues", "topImprovements", "strengths")
_SENTINELS = {"none", "none found", "n/a", "na", "not applicable", "nothing"}
# Only whole-entry claims of absence: "No dates on Education" or "No headings, a major issue" are real.
_NO_ISSUES = re.compile(
    r"^(?:there (?:are|were) )?no "
    r"(?:(?:specific|major|obvious|significant|notable|apparent|other|known|ats|formatting|format|parsing|layout)[ -])*"
    r"(?:issues?|problems?|concerns?)"
    r"(?: (?:were |was |are |have been )?(?:found|detected|identified|noted|present))?"
    r"(?: (?:in|with) (?:the |this )?(?:cv|resume|document))?$"
)


def parse_result(raw_model_output: str) -> AnalysisResult:
    """Parse and repair the model's reply into a validated result; raise ResultParseError if it can't.

    Renders reportMarkdown from the validated fields; the model is never asked for it.
    """
    result_data = _load_json(raw_model_output)
    result_data["breakdown"] = _coerce_breakdown(result_data.get("breakdown"))
    result_data["score"] = sum(item["score"] for item in result_data["breakdown"])
    result_data["band"] = Band.for_score(result_data["score"]).value

    for field in _LIST_FIELDS:
        value = result_data.get(field)
        result_data[field] = value if isinstance(value, list) else []
    result_data["matchedKeywords"] = _dedupe(
        [str(k) for k in result_data["matchedKeywords"] if str(k).strip()], _norm
    )
    result_data["formattingIssues"] = _dedupe(
        [str(k) for k in result_data["formattingIssues"] if str(k).strip() and not _is_sentinel(str(k))], _norm
    )
    result_data["strengths"] = _dedupe([str(k) for k in result_data["strengths"] if str(k).strip()], _norm)
    result_data["missingKeywords"] = _drop_contradictions(
        _dedupe([_coerce_missing(k) for k in result_data["missingKeywords"]], _missing_key),
        result_data["matchedKeywords"],
    )
    result_data["topImprovements"] = [
        i for i in result_data["topImprovements"] if not _is_degenerate(i)
    ][:MAX_IMPROVEMENTS]

    result_data["reportMarkdown"] = "pending"  # placeholder until the validated result can be rendered

    try:
        result = AnalysisResult.model_validate(result_data)
    except ValidationError as exc:
        raise ResultParseError(_summarise(exc)) from None
    return result.model_copy(update={"reportMarkdown": render_report_markdown(result)})


def _load_json(raw: str) -> dict[str, Any]:
    text = _FENCE.sub("", raw.strip()).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ResultParseError("no JSON object in model output")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ResultParseError(f"invalid JSON: {exc.msg} at line {exc.lineno}") from None
    if not isinstance(data, dict):
        raise ResultParseError("model output is not a JSON object")
    return data


def _coerce_breakdown(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise ResultParseError("breakdown is missing or not a list")
    by_category: dict[str, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, dict) and item.get("category") in RUBRIC:
            by_category.setdefault(item["category"], item)
    missing = [c for c in RUBRIC if c not in by_category]
    if missing:
        raise ResultParseError(f"breakdown missing categories: {', '.join(missing)}")

    out = []
    for category, maximum in RUBRIC.items():
        item = by_category[category]
        out.append(
            {
                "category": category,
                "score": _clamp(_to_int(item.get("score"), category), 0, maximum),
                "max": maximum,
                "reason": str(item.get("reason") or "").strip(),
            }
        )
    return out


def _to_int(value: Any, category: str) -> int:
    if isinstance(value, bool):
        raise ResultParseError(f"{category} score is not a number")
    try:
        return round(float(value))
    except (TypeError, ValueError):
        raise ResultParseError(f"{category} score is not a number") from None


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _coerce_missing(item: Any) -> Any:
    if not isinstance(item, dict):
        return item
    item = dict(item)
    if isinstance(item.get("requirement"), str):
        item["requirement"] = item["requirement"].strip().lower()
    where = item.get("whereToAdd")
    if isinstance(where, str) and where.strip().lower() in {"skill gap", "skill-gap", "n/a", "none", ""}:
        item["whereToAdd"] = None
        item["skillGap"] = True
    return item


def _drop_contradictions(missing: list[Any], matched: list[str]) -> list[Any]:
    """Small models sometimes list a keyword as both matched and missing; matched wins."""
    found = {k.strip().casefold() for k in matched}
    return [
        item
        for item in missing
        if not (isinstance(item, dict) and str(item.get("keyword", "")).strip().casefold() in found)
    ]


def _squash(value: Any) -> str:
    return " ".join(str(value).split())


def _norm(value: Any) -> str:
    return _squash(value).casefold()


def _dedupe(items: list[Any], key: Callable[[Any], str]) -> list[Any]:
    """Small models loop; keep the first of each repeated item, in order."""
    seen: set[str] = set()
    unique = []
    for item in items:
        if (marker := key(item)) not in seen:
            seen.add(marker)
            unique.append(item)
    return unique


def _missing_key(item: Any) -> str:
    # Non-dicts pass through so validation rejects them and the reformat retry still runs.
    return _norm(item.get("keyword", "") if isinstance(item, dict) else item)


def _is_sentinel(text: str) -> bool:
    """An entry that says there is nothing to report; absence is an empty list."""
    normalised = _norm(text).rstrip(".!")
    return normalised in _SENTINELS or _NO_ISSUES.match(normalised) is not None


def _is_degenerate(item: Any) -> bool:
    """An improvement that rewrites nothing or lacks its text. Case-only edits count as rewrites."""
    if not isinstance(item, dict):  # structural: left for validation to reject
        return False
    section, original, suggested = (_squash(item.get(k) or "") for k in ("section", "original", "suggested"))
    return not (section and original and suggested) or original == suggested


def _summarise(exc: ValidationError) -> str:
    first = exc.errors()[0]
    location = ".".join(str(p) for p in first["loc"])
    return f"{exc.error_count()} schema error(s); first at {location}: {first['msg']}"


def render_report_markdown(result: AnalysisResult) -> str:
    """Render a readable Markdown report from the validated structured fields.

    Each section helper owns its own leading blank line, so concatenating them yields the spacing.
    Optional sections return no lines when their field is empty.
    """
    lines: list[str] = []
    for section in (
        _header_section(result),
        _breakdown_section(result),
        _matched_keywords_section(result),
        _missing_keywords_section(result),
        _formatting_issues_section(result),
        _improvements_section(result),
        _strengths_section(result),
        _revised_summary_section(result),
    ):
        lines += section
    return "\n".join(lines)


def _header_section(result: AnalysisResult) -> list[str]:
    """Title, overall score and band, and the summary."""
    return ["# ATS assessment", "", f"**Score:** {result.score}/100 — **{result.band.value}**", "", result.summary]


def _breakdown_section(result: AnalysisResult) -> list[str]:
    """The per-category score table (always present)."""
    lines = ["", "## Breakdown", "", "| Category | Score | Reason |", "|---|---|---|"]
    for item in result.breakdown:
        label = item.category.replace("_", " ").capitalize()
        lines.append(f"| {label} | {item.score}/{item.max} | {item.reason} |")
    return lines


def _matched_keywords_section(result: AnalysisResult) -> list[str]:
    """Keywords found in the CV, or nothing when there are none."""
    if not result.matchedKeywords:
        return []
    return ["", "## Matched keywords", "", ", ".join(result.matchedKeywords)]


def _missing_keywords_section(result: AnalysisResult) -> list[str]:
    """Keywords absent from the CV, each marked a skill gap or placed to add."""
    if not result.missingKeywords:
        return []
    lines = ["", "## Missing keywords", ""]
    for kw in result.missingKeywords:
        hint = "skill gap" if kw.skillGap else f"add to: {kw.whereToAdd}"
        lines.append(f"- **{kw.keyword}** ({kw.requirement.value}) — {hint}")
    return lines


def _formatting_issues_section(result: AnalysisResult) -> list[str]:
    """ATS formatting problems, or nothing when there are none."""
    if not result.formattingIssues:
        return []
    return ["", "## Formatting issues", "", *[f"- {i}" for i in result.formattingIssues]]


def _improvements_section(result: AnalysisResult) -> list[str]:
    """Suggested rewrites, numbered, with original and suggested text."""
    if not result.topImprovements:
        return []
    lines = ["", "## Top improvements", ""]
    for n, imp in enumerate(result.topImprovements, 1):
        lines += [
            f"{n}. **{imp.section}** — {imp.problem}",
            f"   - Original: {imp.original}",
            f"   - Suggested: {imp.suggested}",
        ]
    return lines


def _strengths_section(result: AnalysisResult) -> list[str]:
    """The CV's strengths, or nothing when there are none."""
    if not result.strengths:
        return []
    return ["", "## Strengths", "", *[f"- {s}" for s in result.strengths]]


def _revised_summary_section(result: AnalysisResult) -> list[str]:
    """The rewritten summary (always present), with a trailing blank line."""
    return ["", "## Revised summary", "", result.revisedSummary, ""]
