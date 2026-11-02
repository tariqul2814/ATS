import hashlib
import hmac

from app.pipeline.sign import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign, sign_now

# Vector shared with ATS_Web_API.Tests/HmacWebhookSignatureVerifierTests; expected hex was computed
# with .NET's HMACSHA256 (the orchestrator's primitive), not with Python.
SECRET = "integration-test-secret-0123456789"
BODY = b'{"analysisId":"abc","status":"Completed"}'
TS = 1791892800  # 2026-10-13T12:00:00Z
EXPECTED = "37ba52aa44ffc0a8f6b6cb4f7108b7ba61302fb0c15eaf46efee901e7e08bb8d"


def orchestrator_verify(body: bytes, ts: str, sig: str, secret: str, now: int, tolerance: int = 300) -> bool:
    """Port of HmacWebhookSignatureVerifier.Verify, used to check round-trips."""
    if not ts or not sig or abs(now - int(ts)) > tolerance:
        return False
    hex_sig = sig[len("sha256="):] if sig.lower().startswith("sha256=") else sig
    try:
        provided = bytes.fromhex(hex_sig)
    except ValueError:
        return False
    computed = hmac.new(secret.encode("utf-8"), ts.encode("ascii") + b"." + body, hashlib.sha256).digest()
    return hmac.compare_digest(provided, computed)


def test_known_vector_matches_dotnet():
    headers = sign(BODY, SECRET, TS)
    assert headers == {SIGNATURE_HEADER: EXPECTED, TIMESTAMP_HEADER: "1791892800"}


def test_lowercase_hex_of_sha256_length():
    sig = sign(BODY, SECRET, TS)[SIGNATURE_HEADER]
    assert sig == sig.lower() and len(sig) == 64


def test_round_trip_through_orchestrator_scheme():
    h = sign(BODY, SECRET, TS)
    assert orchestrator_verify(BODY, h[TIMESTAMP_HEADER], h[SIGNATURE_HEADER], SECRET, now=TS)


def test_tampered_body_or_wrong_secret_fails_verification():
    h = sign(BODY, SECRET, TS)
    assert not orchestrator_verify(BODY + b" ", h[TIMESTAMP_HEADER], h[SIGNATURE_HEADER], SECRET, now=TS)
    assert not orchestrator_verify(BODY, h[TIMESTAMP_HEADER], h[SIGNATURE_HEADER], "other", now=TS)


def test_timestamp_is_part_of_the_signature():
    assert sign(BODY, SECRET, TS)[SIGNATURE_HEADER] != sign(BODY, SECRET, TS + 1)[SIGNATURE_HEADER]


def test_sign_now_uses_injected_clock():
    h = sign_now(BODY, SECRET, clock=lambda: TS + 0.9)
    assert h[TIMESTAMP_HEADER] == str(TS)
    assert h[SIGNATURE_HEADER] == EXPECTED


def test_fresh_signature_inside_replay_window():
    h = sign_now(BODY, SECRET, clock=lambda: TS)
    assert orchestrator_verify(BODY, h[TIMESTAMP_HEADER], h[SIGNATURE_HEADER], SECRET, now=TS + 299)
    assert not orchestrator_verify(BODY, h[TIMESTAMP_HEADER], h[SIGNATURE_HEADER], SECRET, now=TS + 301)


def test_non_ascii_body_signed_as_raw_bytes():
    body = '{"summary":"Développeur — 5 ans"}'.encode()
    h = sign(body, SECRET, TS)
    assert orchestrator_verify(body, h[TIMESTAMP_HEADER], h[SIGNATURE_HEADER], SECRET, now=TS)
