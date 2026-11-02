"""Callback signing (Req 10). Mirrors ATS_Web_API's HmacWebhookSignatureVerifier exactly:
HMAC-SHA256(key = UTF-8 secret, message = ASCII "{timestamp}." + raw body bytes), lowercase hex.
"""

import hashlib
import hmac
import time
from collections.abc import Callable

SIGNATURE_HEADER = "X-Signature"
TIMESTAMP_HEADER = "X-Timestamp"

Clock = Callable[[], float]


def sign(body: bytes, secret: str, timestamp: int) -> dict[str, str]:
    """Return the signature and timestamp headers for the body at the given Unix timestamp."""
    ts = str(int(timestamp))
    digest = hmac.new(secret.encode("utf-8"), ts.encode("ascii") + b"." + body, hashlib.sha256)
    return {SIGNATURE_HEADER: digest.hexdigest(), TIMESTAMP_HEADER: ts}


def sign_now(body: bytes, secret: str, clock: Clock = time.time) -> dict[str, str]:
    """Sign with the current time; called once per delivery attempt so retries stay fresh (Req 10.3)."""
    return sign(body, secret, int(clock()))
