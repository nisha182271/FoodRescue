"""Password hashing and signed bearer tokens (standard library only)."""

import base64
import hashlib
import hmac
import json
import secrets
import time

from backend.core.config import SECRET_KEY, TOKEN_TTL_HOURS

PBKDF2_ITERATIONS = 200_000
_ALGORITHM = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    """Return a salted PBKDF2-SHA256 hash string for storage."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return f"{_ALGORITHM}${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a stored hash in constant time."""
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
        if algorithm != _ALGORITHM:
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, expected)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(body: str) -> str:
    digest = hmac.new(
        SECRET_KEY.encode("utf-8"), body.encode("ascii"), hashlib.sha256
    ).digest()
    return _b64encode(digest)


def create_token(user_id: int, role: str) -> str:
    """Issue a signed token carrying the user id, role and expiry."""
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": int(time.time()) + TOKEN_TTL_HOURS * 3600,
    }
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_sign(body)}"


def decode_token(token: str) -> dict | None:
    """Return the token payload if the signature is valid and not expired."""
    try:
        body, signature = token.split(".")
        if not hmac.compare_digest(signature, _sign(body)):
            return None
        payload = json.loads(_b64decode(body).decode("utf-8"))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < int(time.time()):
        return None
    return payload
