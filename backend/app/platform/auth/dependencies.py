from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.platform.auth.api_keys import authenticate_api_key
from app.platform.auth.principal import RequestPrincipal
from app.platform.auth.service import principal_from_access_token
from app.platform.errors import AuthenticationError


def get_request_correlation_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def optional_principal(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> RequestPrincipal | None:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        return principal_from_access_token(db, token)
    if x_api_key:
        return authenticate_api_key(db, x_api_key.strip())
    return None


def require_principal(
    principal: RequestPrincipal | None = Depends(optional_principal),
) -> RequestPrincipal:
    if principal is None:
        raise AuthenticationError()
    return principal


def db_session() -> Generator[Session, None, None]:
    yield from get_db()
