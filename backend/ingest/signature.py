from __future__ import annotations

import hashlib
import hmac


def verify_hmac_signature(
    body: bytes,
    signature: str,
    secret: str,
) -> bool:
    if not secret:
        return True
    supplied = signature.strip()
    if supplied.lower().startswith("sha256="):
        supplied = supplied.split("=", 1)[1]
    expected = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(supplied.lower(), expected)
