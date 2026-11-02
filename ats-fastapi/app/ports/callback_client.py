"""Port for the single HTTP POST of a webhook callback. The delivery stage retries around it."""

from collections.abc import Mapping
from typing import NamedTuple, Protocol


class CallbackResponse(NamedTuple):
    """The orchestrator's reply to one callback POST, reduced to its HTTP status code."""

    status_code: int


class ICallbackClient(Protocol):
    """Posts exact body bytes to the orchestrator's webhook (Req 9). No retry logic (that is the
    pipeline's job, Req 12). Raises CallbackTransportError on connection errors and timeouts."""

    async def post(self, url: str, body: bytes, headers: Mapping[str, str]) -> CallbackResponse:
        """POST the exact body bytes with the given headers; return the response's status code."""
        ...
