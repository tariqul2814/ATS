import json

import pytest

from app.contracts.result import Band
from app.pipeline.errors import ResultParseError
from app.pipeline.parse import parse_result
from tests.conftest import ASSETS

VALID = (ASSETS / "model_output_valid.json").read_text()


def valid_dict() -> dict:
    return json.loads(VALID)


def test_well_formed_output_parses():
    result = parse_result(VALID)
    assert result.score == 72
    assert result.band is Band.GOOD
    assert result.breakdown[0].category == "keyword_match"


def test_report_always_rendered_by_the_service():
    # The asset carries a model-written report; the service replaces it with its own rendering.
    result = parse_result(VALID)
    assert result.reportMarkdown.startswith("# ATS assessment")
    assert "**Score:** 72/100 — **Good**" in result.reportMarkdown


def test_out_of_range_values_coerced():
    result = parse_result((ASSETS / "model_output_out_of_range.json").read_text())
    scores = {c.category: (c.score, c.max) for c in result.breakdown}
    assert scores["keyword_match"] == (35, 35)  # 50 clamped to max
    assert scores["experience_relevance"] == (0, 25)  # -3 clamped to 0
    assert scores["achievements_impact"] == (12, 15)  # "12" -> 12
    assert scores["ats_formatting"] == (15, 15)  # 14.6 -> 15, bogus max replaced
    assert result.score == 35 + 0 + 12 + 15 + 8  # total recomputed, not the model's 140
    assert result.band is Band.GOOD  # derived from score, not the model's "excellent"
    kw = result.missingKeywords[0]
    assert kw.requirement.value == "required" and kw.skillGap and kw.whereToAdd is None


def test_total_and_band_follow_breakdown():
    data = valid_dict()
    data["score"] = 99
    data["band"] = "Strong"
    result = parse_result(json.dumps(data))
    assert result.score == 72 and result.band is Band.GOOD


def test_missing_report_markdown_is_synthesised():
    result = parse_result((ASSETS / "model_output_out_of_range.json").read_text())
    md = result.reportMarkdown
    assert md.startswith("# ATS assessment")
    assert f"**Score:** {result.score}/100" in md
    assert "| Keyword match | 35/35 |" in md
    assert "**Kubernetes** (required) — skill gap" in md
    assert result.revisedSummary in md


def test_code_fences_and_chatter_tolerated():
    result = parse_result("Here you go:\n```json\n" + VALID + "\n```\nHope that helps!")
    assert result.score == 72


def test_missing_lists_default_empty():
    data = valid_dict()
    del data["strengths"], data["formattingIssues"]
    result = parse_result(json.dumps(data))
    assert result.strengths == [] and result.formattingIssues == []


def test_keyword_both_matched_and_missing_is_dropped_from_missing():
    # Seen from the real qwen2.5:3b: "Docker" in matchedKeywords and in missingKeywords.
    data = valid_dict()
    data["missingKeywords"].append({"keyword": " docker ", "requirement": "required", "whereToAdd": "Skills"})
    result = parse_result(json.dumps(data))
    assert [k.keyword for k in result.missingKeywords] == ["Kubernetes", "CI/CD"]


def test_improvements_capped_at_five():
    data = valid_dict()
    data["topImprovements"] = data["topImprovements"] * 8
    assert len(parse_result(json.dumps(data)).topImprovements) == 5


def test_repeated_missing_keyword_kept_once():
    # Seen from the real qwen2.5:3b: one required keyword repeated until the list cap.
    data = valid_dict()
    repeats = [" Postgres", "postgres", "POSTGRES ", "Post  gres"]
    data["missingKeywords"] += [{"keyword": k, "requirement": "required", "whereToAdd": "Skills"} for k in repeats]
    result = parse_result(json.dumps(data))
    assert [k.keyword for k in result.missingKeywords] == ["Kubernetes", "CI/CD", " Postgres", "Post  gres"]


def test_repeats_of_a_matched_keyword_all_dropped_from_missing():
    data = valid_dict()
    data["missingKeywords"] += [{"keyword": "Docker", "requirement": "required", "whereToAdd": "Skills"}] * 3
    result = parse_result(json.dumps(data))
    assert [k.keyword for k in result.missingKeywords] == ["Kubernetes", "CI/CD"]


def test_string_lists_deduplicated_keeping_first_in_order():
    data = valid_dict()
    data["matchedKeywords"] = ["Python", "Docker", "python ", "DOCKER", "SQL"]
    data["strengths"] = ["Clear layout", "Strong API work", "clear  layout"]
    data["formattingIssues"] = ["Skills are inline.", "skills are  INLINE.", "Dates are unclear."]
    result = parse_result(json.dumps(data))
    assert result.matchedKeywords == ["Python", "Docker", "SQL"]
    assert result.strengths == ["Clear layout", "Strong API work"]
    assert result.formattingIssues == ["Skills are inline.", "Dates are unclear."]


@pytest.mark.parametrize(
    "sentinel",
    [
        "No specific ATS formatting issues found.",
        "No issues",
        "no formatting problems detected",
        "There are no formatting issues.",
        "No issues found in the CV.",
        "None",
        "N/A",
        "Not applicable.",
    ],
)
def test_sentinel_formatting_entry_removed(sentinel):
    data = valid_dict()
    data["formattingIssues"] = [sentinel] * 3
    assert parse_result(json.dumps(data)).formattingIssues == []


@pytest.mark.parametrize(
    "issue",
    [
        "No dates on the Education section",
        "No section headings, a major ATS issue",
        "No issues with dates, but the Skills section is missing",
        "Nothing separates the job titles from the dates",
        "Known issues with table parsing",
    ],
)
def test_real_formatting_issue_kept(issue):
    data = valid_dict()
    data["formattingIssues"] = [issue, "No issues found"]
    assert parse_result(json.dumps(data)).formattingIssues == [issue]


def test_noop_improvement_dropped_and_cap_applied_afterwards():
    data = valid_dict()
    real = [
        {"section": "S", "problem": "P", "original": f"text {n}", "suggested": f"better {n}"} for n in range(6)
    ]
    noop = {"section": "S", "problem": "P", "original": "Built  an\nAPI.", "suggested": " Built an API. "}
    data["topImprovements"] = [noop, noop, real[0], noop, *real[1:]]
    result = parse_result(json.dumps(data))
    assert [i.original for i in result.topImprovements] == [f"text {n}" for n in range(5)]


def test_case_only_rewrite_is_a_real_change():
    data = valid_dict()
    data["topImprovements"] = [{"section": "S", "problem": "P", "original": "built apis", "suggested": "Built APIs"}]
    assert len(parse_result(json.dumps(data)).topImprovements) == 1


@pytest.mark.parametrize(
    "item",
    [
        {"section": "S", "problem": "P", "original": "text"},
        {"section": "S", "problem": "P", "original": "text", "suggested": None},
        {"section": "S", "problem": "P", "original": "text", "suggested": "   "},
        {"section": "S", "problem": "P", "original": "", "suggested": "text"},
        {"section": None, "problem": "P", "original": "text", "suggested": "better"},
    ],
)
def test_incomplete_improvement_dropped(item):
    data = valid_dict()
    data["topImprovements"].append(item)
    assert len(parse_result(json.dumps(data)).topImprovements) == 1


def test_all_improvements_degenerate_yields_empty_list():
    data = valid_dict()
    data["topImprovements"] = [{"section": "S", "problem": "P", "original": "same", "suggested": "same"}]
    result = parse_result(json.dumps(data))
    assert result.topImprovements == []
    assert "## Top improvements" not in result.reportMarkdown


@pytest.mark.parametrize(
    "field, junk",
    [
        ("missingKeywords", "Postgres"),
        ("topImprovements", "rewrite the summary"),
    ],
)
def test_non_object_items_stay_structural_errors(field, junk):
    # Must surface as ResultParseError so run.py's reformat retry still fires.
    data = valid_dict()
    data[field].append(junk)
    with pytest.raises(ResultParseError, match=field):
        parse_result(json.dumps(data))


def test_cleanup_is_applied_to_the_rendered_report():
    data = valid_dict()
    data["missingKeywords"] += [{"keyword": "Terraform", "requirement": "required", "whereToAdd": "Skills"}] * 3
    data["formattingIssues"] = ["No specific ATS formatting issues found."]
    md = parse_result(json.dumps(data)).reportMarkdown
    assert md.count("**Terraform**") == 1
    assert "## Formatting issues" not in md


@pytest.mark.parametrize(
    "raw",
    [
        (ASSETS / "model_output_malformed.txt").read_text(),
        "",
        "{ not json at all }",
        "[1, 2, 3]",
    ],
)
def test_unparseable_output_raises_result_parse_error(raw):
    with pytest.raises(ResultParseError) as err:
        parse_result(raw)
    assert err.value.reason == "result_unparseable"


def test_missing_category_rejected_not_invented():
    data = valid_dict()
    data["breakdown"] = data["breakdown"][:4]
    with pytest.raises(ResultParseError, match="education_certifications"):
        parse_result(json.dumps(data))


def test_non_numeric_score_rejected():
    data = valid_dict()
    data["breakdown"][0]["score"] = "high"
    with pytest.raises(ResultParseError, match="not a number"):
        parse_result(json.dumps(data))


def test_missing_required_text_field_rejected():
    data = valid_dict()
    del data["revisedSummary"]
    with pytest.raises(ResultParseError, match="revisedSummary"):
        parse_result(json.dumps(data))
