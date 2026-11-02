import pytest
from pydantic import ValidationError

from app.config import Settings


def make(**overrides) -> Settings:
    values = {"webhook": {"secret": "test-secret"}}
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_defaults_load_with_secret():
    s = make()
    assert s.ollama.model == "qwen2.5:3b"
    assert s.ollama.num_ctx == 16384
    assert s.input.max_cv_chars == 24000
    assert s.input.max_jd_chars == 8000
    assert s.input.hard_ceiling_chars == 120000
    assert s.callback.retry_count == 3
    assert s.webhook.secret.get_secret_value() == "test-secret"


def test_missing_secret_fails(monkeypatch):
    monkeypatch.delenv("APP_WEBHOOK__SECRET", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_empty_secret_fails():
    with pytest.raises(ValidationError):
        make(webhook={"secret": ""})


def test_secret_read_from_env(monkeypatch):
    monkeypatch.setenv("APP_WEBHOOK__SECRET", "from-env")
    monkeypatch.setenv("APP_OLLAMA__MODEL", "qwen2.5:7b")
    s = Settings(_env_file=None)
    assert s.webhook.secret.get_secret_value() == "from-env"
    assert s.ollama.model == "qwen2.5:7b"


def test_num_ctx_below_budget_fails():
    with pytest.raises(ValidationError, match="num_ctx"):
        make(ollama={"num_ctx": 4096})


def test_raising_cap_without_num_ctx_fails():
    with pytest.raises(ValidationError, match="num_ctx"):
        make(input={"max_cv_chars": 60000})


def test_raising_cap_with_num_ctx_passes():
    s = make(input={"max_cv_chars": 60000}, ollama={"num_ctx": 32768})
    assert s.input.max_cv_chars == 60000


def test_ceiling_below_cap_fails():
    with pytest.raises(ValidationError, match="hard_ceiling"):
        make(input={"hard_ceiling_chars": 1000})


def test_analysis_budget_leaves_room_for_callback_retries():
    s = make()
    # 600s orchestrator timeout - (4 attempts x 10s + backoff 3+6+12) - 15s margin
    assert s.analysis_budget_seconds() == 600 - (40 + 21) - 15
    assert s.analysis_budget_seconds() >= s.llm.timeout_seconds


def test_llm_timeout_must_fit_inside_the_budget():
    with pytest.raises(ValidationError, match="dispatch timeout"):
        make(llm={"timeout_seconds": 560})
    with pytest.raises(ValidationError, match="dispatch timeout"):
        make(orchestrator_dispatch_timeout_seconds=300)
