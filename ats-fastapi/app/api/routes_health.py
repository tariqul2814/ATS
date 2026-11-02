"""GET /health (liveness) and GET /ready (readiness) — Req 18."""

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

READY_CACHE_SECONDS = 10.0


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe: always 200 while the process is up."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """Readiness probe: 200 only when Ollama and storage are both reachable (result cached briefly)."""
    state = request.app.state
    now = asyncio.get_running_loop().time()
    cached = getattr(state, "ready_cache", None)
    if cached is None or now - cached[0] > READY_CACHE_SECONDS:
        ollama_ok, storage_ok = await asyncio.gather(
            state.components.llm.check_ready(), state.components.file_store.check_ready()
        )
        cached = (now, ollama_ok, storage_ok)
        state.ready_cache = cached
    _, ollama_ok, storage_ok = cached
    is_ready = ollama_ok and storage_ok
    body = {
        "status": "ready" if is_ready else "not_ready",
        "ollama": "up" if ollama_ok else "down",
        "model": state.model,
        "storage": "accessible" if storage_ok else "inaccessible",
    }
    return JSONResponse(body, status_code=200 if is_ready else 503)
