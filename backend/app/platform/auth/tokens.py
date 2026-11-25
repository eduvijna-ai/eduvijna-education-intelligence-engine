from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import get_settings

ACCESS_TOKEN_TTL_SECONDS = 900
REFRESH_TOKEN_TTL_SECONDS = 86_400


@dataclass(frozen=True, slots=True)
class TokenClaims:
    sub: str
    organization_id: str
    institution_id: str | None
    role: str
    scopes: tuple[str, ...]
    actor_kind: str
    actor_ref: str
    jti: str
    exp: int
    session_epoch: int


def _signing_key() -> bytes:
    return get_settings().api_secret_key.encode("utf-8")


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_access_token(claims: TokenClaims) -> str:
    payload = {
        "sub": claims.sub,
        "organization_id": claims.organization_id,
        "institution_id": claims.institution_id,
        "role": claims.role,
        "scopes": list(claims.scopes),
        "actor_kind": claims.actor_kind,
        "actor_ref": claims.actor_ref,
        "jti": claims.jti,
        "exp": claims.exp,
        "session_epoch": claims.session_epoch,
        "typ": "access",
    }
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    sig = hmac.new(_signing_key(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def decode_access_token(token: str) -> TokenClaims:
    try:
        body, sig = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Malformed access token") from exc
    expected = hmac.new(_signing_key(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise ValueError("Invalid access token signature")
    payload: dict[str, Any] = json.loads(base64.urlsafe_b64decode(body + "=="))
    if payload.get("typ") != "access":
        raise ValueError("Wrong token type")
    exp = int(payload["exp"])
    if exp < 0 or exp > 2_000_000_000:
        raise ValueError("Access token expiry out of bounds")
    if datetime.now(UTC).timestamp() > exp:
        raise ValueError("Access token expired")
    epoch = int(payload.get("session_epoch", -1))
    if epoch < 0:
        raise ValueError("Access token missing session epoch")
    return TokenClaims(
        sub=str(payload["sub"]),
        organization_id=str(payload["organization_id"]),
        institution_id=payload.get("institution_id"),
        role=str(payload["role"]),
        scopes=tuple(str(s) for s in payload.get("scopes", [])),
        actor_kind=str(payload["actor_kind"]),
        actor_ref=str(payload["actor_ref"]),
        jti=str(payload["jti"]),
        exp=exp,
        session_epoch=epoch,
    )


def build_access_claims(
    *,
    principal_id: str,
    organization_id: str,
    institution_id: str | None,
    role: str,
    scopes: tuple[str, ...],
    actor_kind: str,
    actor_ref: str,
    session_epoch: int,
) -> tuple[TokenClaims, str]:
    jti = uuid.uuid4().hex
    exp = int((datetime.now(UTC) + timedelta(seconds=ACCESS_TOKEN_TTL_SECONDS)).timestamp())
    claims = TokenClaims(
        sub=principal_id,
        organization_id=organization_id,
        institution_id=institution_id,
        role=role,
        scopes=scopes,
        actor_kind=actor_kind,
        actor_ref=actor_ref,
        jti=jti,
        exp=exp,
        session_epoch=session_epoch,
    )
    return claims, issue_access_token(claims)


def issue_refresh_token() -> str:
    return secrets.token_urlsafe(48)
