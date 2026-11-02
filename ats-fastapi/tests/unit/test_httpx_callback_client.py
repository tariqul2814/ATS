import httpx
import pytest
import respx

from app.adapters.httpx_callback_client import HttpxCallbackClient
from app.pipeline.errors import CallbackTransportError

URL = "https://ats.test/api/webhooks/analysis-completed"
BODY = '{"analysisId":"x","summary":"Développeur"}'.encode()


@respx.mock
async def test_posts_exact_bytes_and_headers():
    route = respx.post(URL).mock(return_value=httpx.Response(200))
    response = await HttpxCallbackClient(5).post(URL, BODY, {"X-Signature": "abc", "X-Timestamp": "1"})
    assert response.status_code == 200
    request = route.calls.last.request
    assert request.content == BODY
    assert request.headers["X-Signature"] == "abc"
    assert request.headers["X-Timestamp"] == "1"
    assert request.headers["Content-Type"] == "application/json"


@respx.mock
@pytest.mark.parametrize("status", [400, 401, 404, 500, 503])
async def test_status_surfaced_not_raised(status):
    respx.post(URL).mock(return_value=httpx.Response(status))
    assert (await HttpxCallbackClient(5).post(URL, BODY, {})).status_code == status


@respx.mock
@pytest.mark.parametrize("error", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")])
async def test_transport_errors_raised(error):
    respx.post(URL).mock(side_effect=error)
    with pytest.raises(CallbackTransportError):
        await HttpxCallbackClient(5).post(URL, BODY, {})
