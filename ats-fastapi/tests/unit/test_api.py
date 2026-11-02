"""Endpoint tests with fake adapters injected through the app factory (Req 1, 2, 18, 22.4)."""

import asyncio
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import ConfigurationError, Settings, get_settings
from app.main import Components, create_app
from app.pipeline.extract import FileType
from tests.conftest import ASSETS
from tests.fakes import FakeCallbackClient, FakeFileStore, FakeLlmClient, FakeTrackingRepository

REF = r"C:\ats\storage\cv.pdf"
VALID_OUTPUT = (ASSETS / "model_output_valid.json").read_text()
PROJECT = Path(__file__).resolve().parents[2]


def dispatch_body(**overrides) -> dict:
    body = {
        "analysisId": str(uuid.uuid4()),
        "resumeFileReference": REF,
        "jobDescription": "Senior Python engineer with FastAPI and PostgreSQL",
        "callbackUrl": "https://ats.test/api/webhooks/analysis-completed",
    }
    body.update(overrides)
    return body


def make_components(**kw) -> Components:
    return Components(
        file_store=kw.get("file_store") or FakeFileStore({REF: ((ASSETS / "sample_cv.pdf").read_bytes(), FileType.PDF)}),
        llm=kw.get("llm") or FakeLlmClient(*([VALID_OUTPUT] * 5)),
        callback_client=kw.get("callback") or FakeCallbackClient(200),
        tracking=kw.get("tracking") or FakeTrackingRepository(),
    )


def make_app(components: Components | None = None, **settings_overrides):
    settings = Settings(_env_file=None, webhook={"secret": "test-secret"}, **settings_overrides)
    comps = components or make_components()
    return create_app(settings, comps, setup_logging=False), comps


def test_valid_dispatch_returns_202_and_runs_in_background():
    app, comps = make_app()
    body = dispatch_body()
    with TestClient(app) as client:
        response = client.post("/analyze", json=body)
    assert response.status_code == 202
    assert response.json() == {"analysisId": body["analysisId"], "status": "accepted"}
    [(url, raw, headers)] = comps.callback_client.posts  # TestClient waits for background tasks
    assert url == body["callbackUrl"]
    callback = json.loads(raw)
    assert callback["status"] == "Completed" and callback["analysisId"] == body["analysisId"]
    assert {"X-Signature", "X-Timestamp"} <= set(headers)


async def test_ack_is_sent_before_the_llm_runs():
    events: list[str] = []
    llm = FakeLlmClient(VALID_OUTPUT)
    original = llm.complete

    async def tracking_complete(messages, *, json_mode=True):
        events.append("llm-start")
        return await original(messages, json_mode=json_mode)

    llm.complete = tracking_complete
    app, _ = make_app(make_components(llm=llm))
    payload = json.dumps(dispatch_body()).encode()
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
        "scheme": "http", "path": "/analyze", "raw_path": b"/analyze", "query_string": b"",
        "root_path": "", "client": ("test", 1), "server": ("test", 80),
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())],
    }
    sent_request = False

    async def receive():
        nonlocal sent_request
        if not sent_request:
            sent_request = True
            return {"type": "http.request", "body": payload, "more_body": False}
        await asyncio.sleep(3600)

    async def send(message):
        events.append(message["type"] + (f":{message['status']}" if "status" in message else ""))

    async with app.router.lifespan_context(app):
        await asyncio.wait_for(app(scope, receive, send), timeout=10)

    assert events.index("http.response.start:202") < events.index("http.response.body") < events.index("llm-start")


@pytest.mark.parametrize(
    "overrides",
    [
        {"analysisId": "not-a-guid"},
        {"resumeFileReference": ""},
        {"jobDescription": "   "},
        {"callbackUrl": "not a url"},
    ],
)
def test_invalid_body_422_and_nothing_started(overrides):
    app, comps = make_app()
    with TestClient(app) as client:
        response = client.post("/analyze", json=dispatch_body(**overrides))
    assert response.status_code == 422
    assert comps.llm.calls == [] and comps.callback_client.posts == [] and comps.tracking.records == {}


@pytest.mark.parametrize("missing", ["analysisId", "resumeFileReference", "jobDescription", "callbackUrl"])
def test_missing_field_422(missing):
    app, comps = make_app()
    body = dispatch_body()
    del body[missing]
    with TestClient(app) as client:
        response = client.post("/analyze", json=body)
    assert response.status_code == 422
    assert comps.callback_client.posts == []


def test_422_does_not_echo_inputs():
    app, _ = make_app()
    secret_jd = "CONFIDENTIAL-JD-TEXT"
    with TestClient(app) as client:
        response = client.post("/analyze", json=dispatch_body(jobDescription=secret_jd, analysisId="bad"))
    assert response.status_code == 422
    assert secret_jd not in response.text
    assert response.json()["detail"][0]["loc"] == ["body", "analysisId"]


def test_dispatch_token_enforced_when_configured():
    app, comps = make_app(dispatch={"token": "dispatch-token"})
    with TestClient(app) as client:
        assert client.post("/analyze", json=dispatch_body()).status_code == 401
        bad = client.post("/analyze", json=dispatch_body(), headers={"X-Dispatch-Token": "wrong"})
        assert bad.status_code == 401
        good = client.post("/analyze", json=dispatch_body(), headers={"X-Dispatch-Token": "dispatch-token"})
        assert good.status_code == 202
    assert len(comps.callback_client.posts) == 1


def test_at_capacity_returns_503():
    app, comps = make_app(llm={"max_in_flight": 1})
    with TestClient(app) as client:
        app.state.runner.in_flight.add(uuid.uuid4())  # one analysis already running
        response = client.post("/analyze", json=dispatch_body())
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
    assert comps.llm.calls == []


def test_duplicate_in_flight_dispatch_not_run_twice():
    app, comps = make_app()
    body = dispatch_body()
    with TestClient(app) as client:
        app.state.runner.in_flight.add(uuid.UUID(body["analysisId"]))
        response = client.post("/analyze", json=body)
    assert response.status_code == 202
    assert comps.llm.calls == [] and comps.callback_client.posts == []


def test_shutdown_stops_accepting():
    app, _ = make_app()
    with TestClient(app):
        runner = app.state.runner
        assert runner.accepting
    assert not runner.accepting


def test_unhandled_error_is_generic_500():
    tracking = FakeTrackingRepository()

    async def broken(*args, **kwargs):
        raise RuntimeError(r"secret path C:\internal\db")

    tracking.upsert_received = broken
    app, _ = make_app(make_components(tracking=tracking))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/analyze", json=dispatch_body())
    assert response.status_code == 500
    assert response.json() == {"detail": "internal error"}
    assert "internal" not in response.text.replace("internal error", "")


def test_health():
    app, _ = make_app()
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_ready_when_dependencies_up():
    app, _ = make_app()
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "ollama": "up", "model": "fake-model", "storage": "accessible"}


def test_not_ready_when_ollama_down():
    app, _ = make_app(make_components(llm=FakeLlmClient(ready=False)))
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["ollama"] == "down" and response.json()["status"] == "not_ready"


def test_ready_result_is_cached():
    llm = FakeLlmClient(ready=True)
    app, _ = make_app(make_components(llm=llm))
    with TestClient(app) as client:
        assert client.get("/ready").status_code == 200
        llm.ready = False
        assert client.get("/ready").status_code == 200  # cached for a few seconds


def test_app_fails_fast_without_secret(monkeypatch):
    monkeypatch.delenv("APP_WEBHOOK__SECRET", raising=False)
    monkeypatch.chdir(PROJECT / "tests")  # no .env here
    get_settings.cache_clear()
    try:
        with pytest.raises(ConfigurationError, match=r"APP_WEBHOOK__SECRET is not set") as err:
            create_app()
        assert ".env.example" in str(err.value)
    finally:
        get_settings.cache_clear()


def test_invalid_value_names_the_env_var(monkeypatch):
    monkeypatch.setenv("APP_WEBHOOK__SECRET", "s")
    monkeypatch.setenv("APP_LLM__MAX_CONCURRENCY", "0")
    monkeypatch.setenv("APP_OLLAMA__NUM_CTX", "1024")
    monkeypatch.chdir(PROJECT / "tests")
    get_settings.cache_clear()
    try:
        with pytest.raises(ConfigurationError) as err:
            get_settings()
        assert "APP_LLM__MAX_CONCURRENCY" in str(err.value)
    finally:
        get_settings.cache_clear()


def test_importing_the_app_has_no_side_effects():
    env = {k: v for k, v in os.environ.items() if not k.startswith("APP_")}
    code = "import app.main, app.pipeline.run, app.pipeline.prompt; print('ok')"
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=PROJECT / "tests", env={**env, "PYTHONPATH": str(PROJECT)},
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
