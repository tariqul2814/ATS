"""Debug harness router tests (ats-debug-ui spec), all with injected port fakes — no Ollama/network.

Covers: gating (Req 1.2/1.3), each per-stage endpoint (Req 2), the raw LLM endpoint and its error
statuses (Req 3), end-to-end score happy path + partial-on-failure (Req 4), and that enabling the
flag leaves the production routes unchanged (Req 6.4).
"""

import uuid

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import Components, create_app
from app.pipeline.errors import LlmTimeoutError, LlmUnavailableError
from app.pipeline.extract import FileType
from tests.conftest import ASSETS
from tests.fakes import FakeCallbackClient, FakeFileStore, FakeLlmClient, FakeTrackingRepository

REF = r"C:\ats\storage\cv.pdf"
VALID_OUTPUT = (ASSETS / "model_output_valid.json").read_text()
MALFORMED = (ASSETS / "model_output_malformed.txt").read_text()
PDF_BYTES = (ASSETS / "sample_cv.pdf").read_bytes()
JD = "Senior Python engineer with FastAPI and PostgreSQL"


def make_components(**kw) -> Components:
    return Components(
        file_store=kw.get("file_store") or FakeFileStore({REF: (PDF_BYTES, FileType.PDF)}),
        llm=kw.get("llm") or FakeLlmClient(*([VALID_OUTPUT] * 5)),
        callback_client=kw.get("callback") or FakeCallbackClient(200),
        tracking=kw.get("tracking") or FakeTrackingRepository(),
    )


def make_app(components: Components | None = None, enabled: bool = True, **settings_overrides):
    settings = Settings(
        _env_file=None, webhook={"secret": "test-secret"}, debug={"enabled": enabled}, **settings_overrides
    )
    comps = components or make_components()
    return create_app(settings, comps, setup_logging=False), comps


# --- gating ---------------------------------------------------------------------------------


def test_debug_disabled_by_default_404():
    app, _ = make_app(enabled=False)
    with TestClient(app) as client:
        assert client.get("/debug/ping").status_code == 404


def test_debug_enabled_ping():
    app, _ = make_app()
    with TestClient(app) as client:
        response = client.get("/debug/ping")
    assert response.status_code == 200
    assert response.json() == {"debug": True, "model": "fake-model"}


def test_ping_contract_unchanged():
    # Guard: /debug/template must not have leaked the prompt into ping's narrow body.
    app, _ = make_app()
    with TestClient(app) as client:
        response = client.get("/debug/ping")
    assert response.json() == {"debug": True, "model": "fake-model"}


# --- active prompt template -----------------------------------------------------------------


def test_template_returns_active_name_and_unfilled_text():
    app, _ = make_app()
    with TestClient(app) as client:
        response = client.get("/debug/template")
    body = response.json()
    assert response.status_code == 200 and body["ok"]
    assert body["name"] == "ats_rubric_v1"
    assert "{{CV_TEXT}}" in body["user"] and "{{JOB_DESCRIPTION}}" in body["user"]
    assert body["system"]  # the system part is present


def test_template_reflects_configured_template():
    app, _ = make_app(prompt={"template": "ats_rubric_v2"})
    with TestClient(app) as client:
        response = client.get("/debug/template")
    assert response.status_code == 200 and response.json()["name"] == "ats_rubric_v2"


def test_template_404_when_debug_disabled():
    app, _ = make_app(enabled=False)
    with TestClient(app) as client:
        assert client.get("/debug/template").status_code == 404


# --- per-stage ------------------------------------------------------------------------------


def test_extract_from_upload():
    app, _ = make_app()
    with TestClient(app) as client:
        response = client.post("/debug/extract", files={"file": ("cv.pdf", PDF_BYTES, "application/pdf")})
    body = response.json()
    assert response.status_code == 200 and body["ok"] and body["file_type"] == "pdf"
    assert body["chars"] > 0 and len(body["text"]) == body["chars"]


def test_extract_from_reference():
    app, _ = make_app()
    with TestClient(app) as client:
        response = client.post("/debug/extract", data={"reference": REF})
    assert response.status_code == 200 and response.json()["file_type"] == "pdf"


def test_extract_without_input_is_422():
    app, _ = make_app()
    with TestClient(app) as client:
        response = client.post("/debug/extract")
    assert response.status_code == 422 and response.json()["reason"] == "bad_request"


def test_prepare_reports_fields():
    app, _ = make_app()
    with TestClient(app) as client:
        response = client.post("/debug/prepare", json={"cv_text": "Python engineer", "job_description": JD})
    body = response.json()
    assert body["ok"] and body["truncated"] is False
    assert body["original_chars"] == len("Python engineer")


def test_prompt_returns_system_and_user_messages():
    app, _ = make_app()
    with TestClient(app) as client:
        response = client.post("/debug/prompt", json={"cv_text": "Python engineer", "job_description": JD})
    body = response.json()
    assert body["ok"] and len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "system" and "rubric" in body["system"].lower()
    assert "Python engineer" in body["user"] and JD in body["user"]


def test_parse_valid_output():
    app, _ = make_app()
    with TestClient(app) as client:
        response = client.post("/debug/parse", json={"raw": VALID_OUTPUT})
    body = response.json()
    assert body["ok"] and 0 <= body["result"]["score"] <= 100
    assert body["result"]["reportMarkdown"].startswith("# ATS assessment")


def test_parse_malformed_output_gives_reason():
    app, _ = make_app()
    with TestClient(app) as client:
        response = client.post("/debug/parse", json={"raw": MALFORMED})
    assert response.status_code == 422
    assert response.json()["reason"] == "result_unparseable"


# --- LLM (primary goal) ---------------------------------------------------------------------


def test_llm_returns_raw_reply():
    app, comps = make_app(make_components(llm=FakeLlmClient("raw model text, not valid json")))
    with TestClient(app) as client:
        response = client.post("/debug/llm", json={"cv_text": "cv", "job_description": JD})
    body = response.json()
    assert body["ok"] and body["raw"] == "raw model text, not valid json"
    assert "elapsed_seconds" in body
    assert len(comps.llm.calls) == 1  # prepared + prompted once


def test_llm_timeout_is_504():
    app, _ = make_app(make_components(llm=FakeLlmClient(LlmTimeoutError("no reply"))))
    with TestClient(app) as client:
        response = client.post("/debug/llm", json={"cv_text": "cv", "job_description": JD})
    assert response.status_code == 504 and response.json()["reason"] == "llm_timeout"


def test_llm_unreachable_is_503():
    app, _ = make_app(make_components(llm=FakeLlmClient(LlmUnavailableError("down"))))
    with TestClient(app) as client:
        response = client.post("/debug/llm", json={"cv_text": "cv", "job_description": JD})
    assert response.status_code == 503 and response.json()["reason"] == "llm_unreachable"


# --- end-to-end score -----------------------------------------------------------------------


def test_score_upload_happy_path():
    app, _ = make_app()
    with TestClient(app) as client:
        response = client.post(
            "/debug/score",
            files={"file": ("cv.pdf", PDF_BYTES, "application/pdf")},
            data={"job_description": JD},
        )
    body = response.json()
    assert response.status_code == 200 and body["ok"]
    assert body["raw"] == VALID_OUTPUT
    assert 0 <= body["result"]["score"] <= 100
    assert set(body["timings"]) >= {"extract", "prepare", "prompt", "llm", "parse", "total"}
    assert body["truncated"] == {"cv": False, "jd": False}


def test_score_reformats_once_then_parses():
    # First reply is unusable, second is valid: the reformat seam should recover (Req 4.2).
    llm = FakeLlmClient(MALFORMED, VALID_OUTPUT)
    app, _ = make_app(make_components(llm=llm))
    with TestClient(app) as client:
        response = client.post(
            "/debug/score", files={"file": ("cv.pdf", PDF_BYTES, "application/pdf")}, data={"job_description": JD}
        )
    assert response.status_code == 200 and response.json()["ok"]
    assert len(llm.calls) == 2


def test_score_file_missing_returns_reason_and_partial():
    from app.pipeline.errors import FileRetrievalError

    store = FakeFileStore(error=FileRetrievalError("absent"))
    app, _ = make_app(make_components(file_store=store))
    with TestClient(app) as client:
        response = client.post("/debug/score", data={"reference": REF, "job_description": JD})
    assert response.status_code == 404
    assert response.json()["reason"] == "file_not_found"


def test_score_unparseable_after_reformat_returns_partial_raw():
    llm = FakeLlmClient(MALFORMED, MALFORMED)  # both attempts fail
    app, _ = make_app(make_components(llm=llm))
    with TestClient(app) as client:
        response = client.post(
            "/debug/score", files={"file": ("cv.pdf", PDF_BYTES, "application/pdf")}, data={"job_description": JD}
        )
    body = response.json()
    assert response.status_code == 422 and body["reason"] == "result_unparseable"
    assert body["partial"]["raw"] == MALFORMED  # the raw reply is surfaced for inspection


# --- production routes unaffected -----------------------------------------------------------


def test_production_routes_unchanged_with_debug_on():
    app, _ = make_app()
    body = {
        "analysisId": str(uuid.uuid4()),
        "resumeFileReference": REF,
        "jobDescription": JD,
        "callbackUrl": "https://ats.test/api/webhooks/analysis-completed",
    }
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.post("/analyze", json=body).status_code == 202
