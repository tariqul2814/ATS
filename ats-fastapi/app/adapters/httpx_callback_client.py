"""Posts signed callbacks to the orchestrator (Req 9). Retries live in the pipeline, not here."""

from collections.abc import Mapping

import httpx

from app.pipeline.errors import CallbackTransportError
from app.ports.callback_client import CallbackResponse


class HttpxCallbackClient:
    """ICallbackClient backed by httpx; see the port for the contract."""

    def __init__(self, timeout_seconds: float, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    async def post(self, url: str, body: bytes, headers: Mapping[str, str]) -> CallbackResponse:
        """POST the exact signed bytes; raise CallbackTransportError on any transport failure."""
        try:
            # content=body sends these exact bytes — the ones that were signed (Req 10.4).
            response = await self._client.post(
                url, content=body, headers={"Content-Type": "application/json", **headers}
            )
        except httpx.HTTPError as exc:  # connect errors, timeouts, protocol errors
            raise CallbackTransportError(type(exc).__name__) from None
        return CallbackResponse(response.status_code)

    async def aclose(self) -> None:
        """Close the underlying HTTP client on shutdown."""
        await self._client.aclose()
