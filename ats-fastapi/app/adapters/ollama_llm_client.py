"""Ollama-backed LLM client (Req 7)."""

import asyncio
from typing import Any

import httpx
import ollama

from app.config import OllamaSettings
from app.contracts.result import model_output_schema
from app.pipeline.errors import LlmTimeoutError, LlmUnavailableError
from app.pipeline.prompt import ChatMessage

RESULT_SCHEMA: dict[str, Any] = model_output_schema()
READY_PROBE_SECONDS = 5


class OllamaLlmClient:
    """ILlmClient backed by a local Ollama server; see the port for the contract."""

    def __init__(self, settings: OllamaSettings, timeout_seconds: float, client: ollama.AsyncClient | None = None):
        self.model = settings.model
        self._options = {"temperature": settings.temperature, "num_ctx": settings.num_ctx}
        self._structured = settings.structured_output
        self._timeout = timeout_seconds
        self._client = client or ollama.AsyncClient(host=settings.base_url, timeout=timeout_seconds)

    async def complete(self, messages: list[ChatMessage], *, json_mode: bool = True) -> str:
        """Send the messages to Ollama and return its raw reply.

        Raises LlmTimeoutError past the timeout, LlmUnavailableError if Ollama errors or is unreachable.
        """
        fmt: Any = None
        if json_mode:
            fmt = RESULT_SCHEMA if self._structured else "json"
        try:
            async with asyncio.timeout(self._timeout):
                response = await self._client.chat(
                    model=self.model, messages=messages, format=fmt, options=self._options, stream=False
                )
        except (TimeoutError, httpx.TimeoutException):
            raise LlmTimeoutError(f"no reply within {self._timeout:.0f}s") from None
        except ollama.ResponseError as exc:
            detail = "model not available" if exc.status_code == 404 else f"HTTP {exc.status_code}"
            raise LlmUnavailableError(f"Ollama error: {detail}") from None
        except (ConnectionError, httpx.HTTPError) as exc:
            raise LlmUnavailableError(f"Ollama unreachable: {type(exc).__name__}") from None
        return response.message.content or ""

    async def check_ready(self) -> bool:
        """True when Ollama responds and has the configured model pulled."""
        try:
            listing = await asyncio.wait_for(self._client.list(), READY_PROBE_SECONDS)
        except Exception:  # noqa: BLE001 — a readiness probe reports "down", it never raises
            return False
        names = {m.model for m in listing.models}
        return self.model in names or f"{self.model}:latest" in names

    async def aclose(self) -> None:
        """Close the underlying Ollama client on shutdown."""
        await self._client.close()
