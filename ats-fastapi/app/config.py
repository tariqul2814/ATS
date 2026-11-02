"""Service configuration (Req 14).

All environment-specific values come from env vars / `.env` with the ``APP_`` prefix and ``__`` as the
nesting delimiter (e.g. ``APP_OLLAMA__MODEL``). Invalid or missing required values fail at startup.
"""

from functools import lru_cache

from pydantic import BaseModel, Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SAFETY_MARGIN_SECONDS = 15


class OllamaSettings(BaseModel):
    """How to reach Ollama and how it should generate: endpoint, model, and decoding options."""

    base_url: str = "http://localhost:11434"
    model: str = "qwen2.5:3b"
    temperature: float = Field(default=0.2, ge=0, le=2)
    num_ctx: int = Field(default=16384, gt=0)
    # True: pass the result JSON schema as Ollama's `format` (grammar-constrained output).
    # False: plain JSON mode (`format="json"`).
    structured_output: bool = True


class LlmSettings(BaseModel):
    """Limits around the model call: per-call timeout, concurrency, and in-flight cap."""

    # Per call. Sized from a measured CPU-only host (qwen2.5:3b: ~25 tok/s prompt, ~6.5 tok/s output):
    # a CV + JD at the input caps takes ~7 min. Each analysis is separately bounded by
    # Settings.analysis_budget_seconds, so a reformat retry only gets the time that remains.
    timeout_seconds: float = Field(default=480, gt=0)
    # 1 for CPU hosts: parallel generations share the same cores and each gets slower.
    max_concurrency: int = Field(default=1, ge=1)
    # Analyses accepted but not yet finished; /analyze returns 503 above this (Req 2.5). Kept low:
    # a deeper queue on slow hardware only turns into llm_timeout failures later.
    max_in_flight: int = Field(default=2, ge=1)


class WebhookSettings(BaseModel):
    """The shared secret used to sign callbacks; must match the orchestrator's."""

    secret: SecretStr = Field(min_length=1)


class CallbackSettings(BaseModel):
    """Retry and timeout policy for delivering the result callback."""

    retry_count: int = Field(default=3, ge=0)
    base_delay_seconds: float = Field(default=2, ge=0)
    timeout_seconds: float = Field(default=10, gt=0)


class InputSettings(BaseModel):
    """Character budgets for the inputs and the token-budget terms derived from them."""

    max_cv_chars: int = Field(default=24000, gt=0)
    max_jd_chars: int = Field(default=8000, gt=0)
    hard_ceiling_chars: int = Field(default=120000, gt=0)
    # Budget terms used to check num_ctx against the caps (design §Input size budget).
    chars_per_token: int = Field(default=4, gt=0)
    prompt_overhead_tokens: int = Field(default=1500, ge=0)
    output_reserve_tokens: int = Field(default=2500, ge=0)

    def required_context_tokens(self) -> int:
        """Estimate the context window the input caps need, including prompt and output reserve."""
        input_tokens = -(-(self.max_cv_chars + self.max_jd_chars) // self.chars_per_token)
        return input_tokens + self.prompt_overhead_tokens + self.output_reserve_tokens


class StorageSettings(BaseModel):
    """How file references resolve to bytes: an optional root and a defensive size bound."""

    # Compatibility shim: when set, a relative resumeFileReference is resolved against this root.
    base_root: str | None = None
    # Defensive bound; the orchestrator already caps uploads at 5 MB (Req 15.2).
    max_file_bytes: int = Field(default=20 * 1024 * 1024, gt=0)


class SqliteSettings(BaseModel):
    """Where the local tracking database file lives."""

    path: str = "./ats_fastapi.db"


class DispatchSettings(BaseModel):
    """Optional shared token that guards POST /analyze when set."""

    # When set, POST /analyze requires a matching X-Dispatch-Token header (Req 15.5).
    token: SecretStr | None = None


class PromptSettings(BaseModel):
    """Which prompt template the scoring stage loads."""

    template: str = "ats_rubric_v1"


class DebugSettings(BaseModel):
    """Whether the unauthenticated developer debug router is mounted, and at what prefix."""

    # When true, create_app mounts the synchronous developer test harness (ats-debug-ui spec).
    # It is unauthenticated and runs the model inline, so it is OFF by default and must stay off
    # in any deployment reachable by untrusted callers.
    enabled: bool = False
    prefix: str = "/debug"


class Settings(BaseSettings):
    """Top-level service configuration, composed from the per-area settings groups."""

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    ollama: OllamaSettings = OllamaSettings()
    llm: LlmSettings = LlmSettings()
    webhook: WebhookSettings
    callback: CallbackSettings = CallbackSettings()
    input: InputSettings = InputSettings()
    storage: StorageSettings = StorageSettings()
    sqlite: SqliteSettings = SqliteSettings()
    dispatch: DispatchSettings = DispatchSettings()
    prompt: PromptSettings = PromptSettings()
    debug: DebugSettings = DebugSettings()
    # The orchestrator fails an analysis whose callback has not arrived after this long (ats-backend Q5).
    orchestrator_dispatch_timeout_seconds: float = Field(default=600, gt=0)

    @model_validator(mode="after")
    def _check_budgets(self) -> "Settings":
        required = self.input.required_context_tokens()
        if self.ollama.num_ctx < required:
            raise ValueError(
                f"ollama.num_ctx={self.ollama.num_ctx} is too small for the input caps "
                f"(needs at least {required} tokens); raise num_ctx or lower the caps"
            )
        if self.input.hard_ceiling_chars < max(self.input.max_cv_chars, self.input.max_jd_chars):
            raise ValueError("input.hard_ceiling_chars must be >= both max_cv_chars and max_jd_chars")
        # The runtime deadline (analysis budget) keeps every callback ahead of the orchestrator's
        # sweeper; this check makes sure that deadline still leaves room for one full LLM call.
        if self.analysis_budget_seconds() < self.llm.timeout_seconds:
            raise ValueError(
                f"only {self.analysis_budget_seconds():.0f}s are left for scoring after callback retries "
                f"within the orchestrator's {self.orchestrator_dispatch_timeout_seconds:.0f}s dispatch timeout; "
                f"that does not fit one LLM call ({self.llm.timeout_seconds:.0f}s)"
            )
        return self

    def callback_worst_case_seconds(self) -> float:
        """Upper bound on callback delivery time across all retries, including back-off and jitter."""
        cb = self.callback
        backoff = sum(cb.base_delay_seconds * 2**i * 1.5 for i in range(cb.retry_count))  # incl. jitter
        return (cb.retry_count + 1) * cb.timeout_seconds + backoff

    def analysis_budget_seconds(self) -> float:
        """Time an analysis may spend queued + scoring and still get its callback to the orchestrator
        before the orchestrator's sweeper fails it."""
        return self.orchestrator_dispatch_timeout_seconds - self.callback_worst_case_seconds() - SAFETY_MARGIN_SECONDS


class ConfigurationError(ValueError):
    """Startup configuration is missing or invalid; the message names the env vars to fix."""


def _env_var(loc: tuple) -> str:
    return "APP_" + "__".join(str(p).upper() for p in loc)


@lru_cache
def get_settings() -> Settings:
    """Load and cache settings; raise ConfigurationError naming the env vars to fix if invalid."""
    try:
        return Settings()
    except ValidationError as exc:
        problems = []
        for err in exc.errors():
            if err["type"] == "missing":
                # A missing nested group (e.g. `webhook`) means its required field is unset.
                loc = err["loc"] + (("secret",) if err["loc"] == ("webhook",) else ())
                problems.append(f"  - {_env_var(loc)} is not set")
            elif err["loc"]:
                problems.append(f"  - {_env_var(err['loc'])}: {err['msg']}")
            else:
                problems.append(f"  - {err['msg'].removeprefix('Value error, ')}")
        raise ConfigurationError(
            "Invalid configuration:\n" + "\n".join(problems) + "\n"
            "Set these as environment variables or in a .env file in the project folder "
            "(see .env.example). APP_WEBHOOK__SECRET must match the orchestrator's Webhook:Secret."
        ) from None
