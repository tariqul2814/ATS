"""App factory and composition root: the only place adapters are bound to ports (Req 13.1).

Run with:  uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.adapters.httpx_callback_client import HttpxCallbackClient
from app.adapters.local_path_file_store import LocalPathFileStore
from app.adapters.ollama_llm_client import OllamaLlmClient
from app.adapters.sqlite_tracking_repo import SqliteTrackingRepository
from app.api import routes_analyze, routes_health
from app.config import Settings, get_settings
from app.observability import configure_logging
from app.pipeline.deliver import CallbackDelivery, RetryPolicy
from app.pipeline.prepare import InputLimits
from app.pipeline.prompt import PromptTemplate, load_template
from app.pipeline.run import AnalysisRunner, PipelineDeps
from app.ports.callback_client import ICallbackClient
from app.ports.file_store import IFileStore
from app.ports.llm_client import ILlmClient
from app.ports.tracking_repo import ITrackingRepository

log = logging.getLogger("ats.app")


@dataclass
class Components:
    """The four adapters bound to their ports; the one seam where tests inject fakes."""

    file_store: IFileStore
    llm: ILlmClient
    callback_client: ICallbackClient
    tracking: ITrackingRepository


def build_components(settings: Settings) -> Components:
    """Construct the production adapters from settings."""
    return Components(
        file_store=LocalPathFileStore(settings.storage.base_root, settings.storage.max_file_bytes),
        llm=OllamaLlmClient(settings.ollama, settings.llm.timeout_seconds),
        callback_client=HttpxCallbackClient(settings.callback.timeout_seconds),
        tracking=SqliteTrackingRepository(settings.sqlite.path),
    )


def create_app(
    settings: Settings | None = None,
    components: Components | None = None,
    *,
    setup_logging: bool = True,
) -> FastAPI:
    """Build the FastAPI app, binding adapters to ports; invalid config fails here at startup."""
    settings = settings or get_settings()  # invalid/missing config fails here, at startup (Req 14.3)
    template = load_template(settings.prompt.template)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if setup_logging:
            _configure_logging_for(settings)
        active_components = components or build_components(settings)
        await _init_tracking(active_components)
        deps = _build_pipeline_deps(settings, active_components, template)
        _publish_app_state(app, settings, active_components, deps, template)
        _log_startup_summary(settings, active_components, template)
        try:
            yield
        finally:
            app.state.runner.accepting = False  # new dispatches get 503 while we shut down (Req 2.5)
            await _close_components(active_components)

    app = FastAPI(title="ATS scoring engine", version="0.1.0", lifespan=lifespan)
    app.include_router(routes_analyze.router)
    app.include_router(routes_health.router)
    _mount_debug_router(app, settings)
    _install_exception_handlers(app)
    return app


def _configure_logging_for(settings: Settings) -> None:
    """Install logging with the webhook and dispatch secrets registered for redaction."""
    token = settings.dispatch.token
    configure_logging(
        secrets=[settings.webhook.secret.get_secret_value(), token.get_secret_value() if token else ""]
    )


async def _init_tracking(components: Components) -> None:
    """Initialise the tracking repository if it exposes an init hook (schema setup)."""
    init = getattr(components.tracking, "init", None)
    if init is not None:
        await init()


def _build_pipeline_deps(settings: Settings, components: Components, template: PromptTemplate) -> PipelineDeps:
    """Assemble the pipeline dependencies from settings and the bound components."""
    return PipelineDeps(
        file_store=components.file_store,
        llm=components.llm,
        delivery=CallbackDelivery(
            components.callback_client,
            settings.webhook.secret.get_secret_value(),
            RetryPolicy(settings.callback.retry_count, settings.callback.base_delay_seconds),
        ),
        tracking=components.tracking,
        template=template,
        limits=InputLimits(
            settings.input.max_cv_chars, settings.input.max_jd_chars, settings.input.hard_ceiling_chars
        ),
        llm_semaphore=asyncio.Semaphore(settings.llm.max_concurrency),
        budget_seconds=settings.analysis_budget_seconds(),
    )


def _publish_app_state(
    app: FastAPI, settings: Settings, components: Components, deps: PipelineDeps, template: PromptTemplate
) -> None:
    """Expose on app.state the shared objects the request handlers read."""
    app.state.settings = settings
    app.state.components = components
    app.state.tracking = components.tracking
    app.state.model = components.llm.model
    app.state.template = template
    app.state.limits = deps.limits
    app.state.runner = AnalysisRunner(deps=deps, max_in_flight=settings.llm.max_in_flight)


def _log_startup_summary(settings: Settings, components: Components, template: PromptTemplate) -> None:
    """Log the one-line summary of the running configuration."""
    log.info(
        "scoring engine started: model=%s num_ctx=%d max_concurrency=%d budget=%.0fs template=%s",
        components.llm.model,
        settings.ollama.num_ctx,
        settings.llm.max_concurrency,
        settings.analysis_budget_seconds(),
        template.name,
    )


async def _close_components(components: Components) -> None:
    """Close each component that exposes an aclose/close hook; log failures, never raise."""
    for resource in (components.llm, components.callback_client, components.tracking):
        close = getattr(resource, "aclose", None) or getattr(resource, "close", None)
        if close is not None:
            try:
                await close()
            except Exception:  # best-effort shutdown: log and keep closing the rest
                log.warning("error while closing %s", type(resource).__name__, exc_info=True)


def _mount_debug_router(app: FastAPI, settings: Settings) -> None:
    """Mount the unauthenticated developer debug router, only when explicitly enabled."""
    if not settings.debug.enabled:
        return
    # Optional developer test harness (ats-debug-ui spec): synchronous, unauthenticated
    # per-stage inspection. Mounted only when explicitly enabled; never in production.
    from app.api import routes_debug

    app.include_router(routes_debug.router, prefix=settings.debug.prefix)
    log.warning("DEBUG API enabled at %s — synchronous & unauthenticated, do not use in production",
                settings.debug.prefix)


def _install_exception_handlers(app: FastAPI) -> None:
    """Register handlers that return terse 422/500 bodies without echoing inputs (Req 15.4)."""

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Field and message only: the default handler echoes inputs back (Req 15.4).
        errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse({"detail": errors}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled_error(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error in request")
        return JSONResponse({"detail": "internal error"}, status_code=500)
