import itertools
import uuid

import pytest

from app.contracts.callback import AnalysisResultCallback
from app.pipeline.deliver import CallbackDelivery, RetryPolicy
from app.pipeline.sign import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign
from app.ports.tracking_repo import CallbackOutcome
from tests.fakes import FakeCallbackClient, transport_error

URL = "https://ats.test/api/webhooks/analysis-completed"
SECRET = "s3cret"
CALLBACK = AnalysisResultCallback.failed(uuid.uuid4(), "llm_timeout")


class Harness:
    def __init__(self, *responses, retry_count=3):
        self.client = FakeCallbackClient(*responses)
        self.sleeps: list[float] = []
        self.ticks = itertools.count(1_000_000, 7)  # each attempt sees a later clock

        async def sleep(seconds):
            self.sleeps.append(seconds)

        self.delivery = CallbackDelivery(
            self.client,
            SECRET,
            RetryPolicy(retry_count=retry_count, base_delay_seconds=2, jitter=0.5),
            clock=lambda: next(self.ticks),
            sleep=sleep,
            rng=lambda: 0.0,
        )

    async def run(self):
        return await self.delivery.deliver(URL, CALLBACK)


async def test_success_first_try():
    h = Harness(200)
    assert await h.run() is CallbackOutcome.DELIVERED
    assert len(h.client.posts) == 1 and h.sleeps == []


async def test_posts_signed_exact_body():
    h = Harness(200)
    await h.run()
    url, body, headers = h.client.posts[0]
    assert url == URL and body == CALLBACK.to_body()
    assert headers == sign(body, SECRET, int(headers[TIMESTAMP_HEADER]))


@pytest.mark.parametrize("transient", [500, 502, 503, 408, 429])
async def test_transient_status_retried_then_succeeds(transient):
    h = Harness(transient, transient, 200)
    assert await h.run() is CallbackOutcome.DELIVERED
    assert len(h.client.posts) == 3


async def test_transport_errors_retried():
    h = Harness(transport_error(), transport_error(), 204)
    assert await h.run() is CallbackOutcome.DELIVERED
    assert len(h.client.posts) == 3


@pytest.mark.parametrize("permanent", [400, 401, 404, 409, 413])
async def test_permanent_rejection_not_retried(permanent):
    h = Harness(permanent, 200)
    assert await h.run() is CallbackOutcome.UNDELIVERED
    assert len(h.client.posts) == 1 and h.sleeps == []


async def test_fresh_timestamp_and_signature_each_attempt():
    h = Harness(503, 503, 200)
    await h.run()
    timestamps = [p[2][TIMESTAMP_HEADER] for p in h.client.posts]
    signatures = [p[2][SIGNATURE_HEADER] for p in h.client.posts]
    assert len(set(timestamps)) == 3 and len(set(signatures)) == 3
    assert len({p[1] for p in h.client.posts}) == 1  # body bytes identical across attempts


async def test_exponential_backoff():
    h = Harness(503, 503, 503, 200)
    await h.run()
    assert h.sleeps == [2.0, 4.0, 8.0]


async def test_jitter_extends_delay():
    assert RetryPolicy(base_delay_seconds=2, jitter=0.5).delay(1, rnd=1.0) == 3.0


async def test_exhaustion_returns_undelivered_and_logs(caplog):
    h = Harness(503, retry_count=2)
    assert await h.run() is CallbackOutcome.UNDELIVERED
    assert len(h.client.posts) == 3
    assert "undelivered after 3 attempts" in caplog.text
    assert SECRET not in caplog.text


async def test_zero_retries_means_single_attempt():
    h = Harness(503, retry_count=0)
    assert await h.run() is CallbackOutcome.UNDELIVERED
    assert len(h.client.posts) == 1
