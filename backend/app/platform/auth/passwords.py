from __future__ import annotations

from app.curator_auth.issuer import hash_operator_secret, verify_operator_secret


def hash_password(plaintext: str) -> dict[str, str]:
    return hash_operator_secret(plaintext)


def verify_password(plaintext: str, stored: dict[str, str]) -> bool:
    return verify_operator_secret(plaintext, stored)
