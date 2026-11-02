"""Signed callback delivery with retries (Req 9, 10, 12)."""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.contracts.callback import AnalysisResultCallback
from app.pipeline.errors import CallbackTransportError
from app.pipeline.sign import Clock, sign_now
from app.ports.callback_client import ICallbackClient
from app.ports.tracking_repo import CallbackOutcome

log = logging.getLogger("ats.callback")

Sleep = Callable[[float], Awaitable[None]]
# 4xx codes that mean "try again later" rather than "never".
RETRYABLE_4XX = frozenset({408, 429})


@dataclass(frozen=True)
class RetryPolicy:
    """How many times to retry a callback and how fast the back-off grows."""

    retry_count: int = 3
    base_delay_seconds: float = 2.0
    jitter: float = 0.5  # each delay grows by up to this fraction

    def delay(self, attempt: int, rnd: float) -> float:
        """Back-off delay before the next attempt: exponential, plus up to `jitter` of random spread."""
        return self.base_delay_seconds * 2 ** (attempt - 1) * (1 + self.jitter * rnd)


class CallbackDelivery:
    """Delivers a signed result callback, retrying transient failures with jittered back-off."""

    def __init__(
        self,
        client: ICallbackClient,
        secret: str,
        policy: RetryPolicy,
        *,
        clock: Clock = time.time,
        sleep: Sleep = asyncio.sleep,
        rng: Callable[[], float] = random.random,
    ):
        self._client = client
        self._secret = secret
        self._policy = policy
        self._clock = clock
        self._sleep = sleep
        self._rng = rng

    async def deliver(self, callback_url: str, callback: AnalysisResultCallback) -> CallbackOutcome:
        """Deliver the signed callback, retrying transient failures until the retry budget is spent."""
        body = callback.to_body()  # serialised once; the same bytes are signed and sent every attempt
        attempts = self._policy.retry_count + 1
        for attempt in range(1, attempts + 1):
            result = await self._attempt(callback_url, body, callback, attempt)
            if isinstance(result, CallbackOutcome):  # delivered, or a permanent rejection
                return result
            await self._back_off(attempt, attempts, result)  # result is the failure detail to log

        log.error(
            "callback undelivered after %d attempts (%s, %d bytes); result kept in tracking DB",
            attempts,
            callback.status,
            len(body),
        )
        return CallbackOutcome.UNDELIVERED

    async def _attempt(
        self, callback_url: str, body: bytes, callback: AnalysisResultCallback, attempt: int
    ) -> CallbackOutcome | str:
        """Make one delivery attempt.

        Returns a terminal CallbackOutcome (delivered, or a permanent rejection), or a detail string
        describing a transient failure the caller should retry.
        """
        headers = sign_now(body, self._secret, self._clock)  # fresh timestamp per attempt (Req 12.3)
        try:
            response = await self._client.post(callback_url, body, headers)
        except CallbackTransportError as error:
            return f"transport error ({error})"
        status = response.status_code
        if 200 <= status < 300:
            log.info("callback delivered (%s, attempt %d, HTTP %d)", callback.status, attempt, status)
            return CallbackOutcome.DELIVERED
        if 400 <= status < 500 and status not in RETRYABLE_4XX:
            log.error("callback rejected with HTTP %d; not retrying (Req 12.2)", status)
            return CallbackOutcome.UNDELIVERED
        return f"HTTP {status}"

    async def _back_off(self, attempt: int, attempts: int, detail: str) -> None:
        """Log the failed attempt and, unless it was the last, sleep for the back-off delay."""
        if attempt < attempts:
            delay = self._policy.delay(attempt, self._rng())
            log.warning("callback attempt %d/%d failed: %s; retrying in %.1fs", attempt, attempts, detail, delay)
            await self._sleep(delay)
        else:
            log.warning("callback attempt %d/%d failed: %s", attempt, attempts, detail)
