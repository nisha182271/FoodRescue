"""Tests for password hashing and signed tokens."""

import base64
import hashlib
import hmac
import json
import time
import unittest

from backend.core import security


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


class PasswordTests(unittest.TestCase):
    def test_hash_round_trip(self):
        stored = security.hash_password("correct-horse")
        self.assertTrue(stored.startswith("pbkdf2_sha256$200000$"))
        self.assertTrue(security.verify_password("correct-horse", stored))

    def test_wrong_password_rejected(self):
        stored = security.hash_password("correct-horse")
        self.assertFalse(security.verify_password("wrong-horse", stored))

    def test_malformed_stored_value_returns_false(self):
        self.assertFalse(security.verify_password("x", "not-a-hash"))
        self.assertFalse(security.verify_password("x", "pbkdf2_sha256$abc$zz$yy"))


class TokenTests(unittest.TestCase):
    def test_token_round_trip(self):
        token = security.create_token(7, "donor")
        payload = security.decode_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["sub"], "7")
        self.assertEqual(payload["role"], "donor")

    def test_tampered_payload_rejected(self):
        token = security.create_token(7, "donor")
        body, sig = token.split(".")
        forged = json.loads(base64.urlsafe_b64decode(body + "=="))
        forged["role"] = "admin"
        self.assertIsNone(
            security.decode_token(f"{_b64(json.dumps(forged).encode())}.{sig}")
        )

    def test_bad_signature_rejected(self):
        token = security.create_token(7, "donor")
        body, _ = token.split(".")
        self.assertIsNone(security.decode_token(f"{body}.AAAA"))

    def test_garbage_rejected(self):
        self.assertIsNone(security.decode_token("garbage"))

    def test_expired_token_rejected(self):
        body = _b64(
            json.dumps(
                {"sub": "7", "role": "donor", "exp": int(time.time()) - 10}
            ).encode()
        )
        sig = _b64(
            hmac.new(
                security.SECRET_KEY.encode(), body.encode(), hashlib.sha256
            ).digest()
        )
        self.assertIsNone(security.decode_token(f"{body}.{sig}"))


if __name__ == "__main__":
    unittest.main()
