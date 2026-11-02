import json
import uuid

import pytest
from pydantic import ValidationError

from app.contracts.callback import AnalysisResultCallback
from app.contracts.dispatch import DispatchRequest
from app.contracts.result import AnalysisResult, Band, MissingKeyword, model_output_schema
from tests.conftest import ASSETS

VALID_DISPATCH = {
    "analysisId": "e3b0c442-98fc-4c1a-9d2b-1f3c5a7e9b10",
    "resumeFileReference": r"C:\ats\storage\e3b0c442.pdf",
    "jobDescription": "Senior Python engineer",
    "callbackUrl": "https://ats.example/api/webhooks/analysis-completed",
}


def valid_result() -> AnalysisResult:
    return AnalysisResult.model_validate_json((ASSETS / "model_output_valid.json").read_text())


def _schema_nodes(node):
    if isinstance(node, dict):
        yield node
        node = list(node.values())
    if isinstance(node, list):
        for child in node:
            yield from _schema_nodes(child)


def test_model_output_schema_bounds_every_list_and_free_text_field():
    # An uncapped field lets the reply run past the LLM timeout (see _MAX_ITEMS in result.py).
    nodes = list(_schema_nodes(model_output_schema()))
    arrays = [n for n in nodes if n.get("type") == "array"]
    texts = [n for n in nodes if n.get("type") == "string" and "enum" not in n and "const" not in n]

    assert arrays and texts
    assert all("maxItems" in n for n in arrays)
    assert all("maxLength" in n for n in texts)


def test_dispatch_well_formed_parses():
    req = DispatchRequest.model_validate(VALID_DISPATCH)
    assert req.analysisId == uuid.UUID(VALID_DISPATCH["analysisId"])
    assert str(req.callbackUrl) == VALID_DISPATCH["callbackUrl"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("analysisId", "not-a-guid"),
        ("resumeFileReference", ""),
        ("resumeFileReference", "   "),
        ("jobDescription", ""),
        ("jobDescription", " \n\t "),
        ("callbackUrl", "not a url"),
        ("callbackUrl", "/relative/path"),
    ],
)
def test_dispatch_rejects_bad_field(field, value):
    with pytest.raises(ValidationError):
        DispatchRequest.model_validate({**VALID_DISPATCH, field: value})


@pytest.mark.parametrize("missing", list(VALID_DISPATCH))
def test_dispatch_rejects_missing_field(missing):
    body = {k: v for k, v in VALID_DISPATCH.items() if k != missing}
    with pytest.raises(ValidationError):
        DispatchRequest.model_validate(body)


def test_result_valid_asset_parses():
    result = valid_result()
    assert result.score == 72
    assert result.band is Band.GOOD
    assert len(result.breakdown) == 5


def test_result_score_bounds():
    data = json.loads((ASSETS / "model_output_valid.json").read_text())
    data["score"] = 101
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(data)


def test_category_score_cannot_exceed_rubric_max():
    data = json.loads((ASSETS / "model_output_valid.json").read_text())
    data["breakdown"][0]["score"] = 36
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(data)


def test_breakdown_must_cover_every_category():
    data = json.loads((ASSETS / "model_output_valid.json").read_text())
    data["breakdown"] = data["breakdown"][:4]
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(data)


def test_missing_keyword_without_guidance_is_skill_gap():
    kw = MissingKeyword(keyword="Go", requirement="preferred")
    assert kw.skillGap is True and kw.whereToAdd is None


def test_completed_callback_shape():
    analysis_id = uuid.uuid4()
    body = json.loads(AnalysisResultCallback.completed(analysis_id, valid_result()).to_body())
    assert set(body) == {"analysisId", "status", "result", "error"}
    assert body["analysisId"] == str(analysis_id)
    assert body["status"] == "Completed"
    assert body["error"] is None
    assert body["result"]["score"] == 72


def test_failed_callback_shape():
    analysis_id = uuid.uuid4()
    body = json.loads(AnalysisResultCallback.failed(analysis_id, "llm_timeout").to_body())
    assert body == {"analysisId": str(analysis_id), "status": "Failed", "result": None, "error": "llm_timeout"}


def test_callback_envelope_rules():
    with pytest.raises(ValidationError):
        AnalysisResultCallback(analysisId=uuid.uuid4(), status="Completed")
    with pytest.raises(ValidationError):
        AnalysisResultCallback(analysisId=uuid.uuid4(), status="Failed")
