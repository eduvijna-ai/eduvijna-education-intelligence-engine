"""Strict disposable PostgreSQL URL validation for C01 Gate B / AT01 tests."""

from __future__ import annotations

import os
from urllib.parse import parse_qsl, urlparse

C01_PG_OPT_IN = "EDUVIJNA_C01_DISPOSABLE_PG"
C01_PG_URL = "EDUVIJNA_C01_DISPOSABLE_DATABASE_URL"
_GENERAL_DATABASE_URL = "DATABASE_URL"
_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost"})
_ALLOWED_PORTS = frozenset({"5432", "55432", "55433"})
_ALLOWED_DRIVERS = frozenset({"postgresql+psycopg", "postgresql"})


def _validate_parsed_disposable_url(raw: str) -> str:
    parsed = urlparse(raw)
    driver = f"{parsed.scheme}"
    if driver not in _ALLOWED_DRIVERS:
        raise ValueError(f"unsupported driver {driver}")
    if parsed.hostname not in _ALLOWED_HOSTS:
        raise ValueError(f"host {parsed.hostname!r} not in disposable allowlist")
    port = str(parsed.port or 5432)
    if port not in _ALLOWED_PORTS:
        raise ValueError(f"port {port} not in disposable allowlist")
    if parse_qsl(parsed.query):
        raise ValueError("query parameters not allowed on disposable PG URL")
    if parsed.fragment:
        raise ValueError("URL fragment not allowed on disposable PG URL")
    if not parsed.path or parsed.path in ("/", ""):
        raise ValueError("database name required in disposable PG URL")
    return raw


def parse_disposable_pg_url(raw: str, *, require_opt_in: bool = True) -> str:
    """Validate dedicated opt-in URL only — never read general DATABASE_URL."""
    if require_opt_in and os.environ.get(C01_PG_OPT_IN) != "1":
        raise ValueError(f"{C01_PG_OPT_IN}=1 required")
    cleaned = raw.strip()
    if not cleaned:
        raise ValueError(f"{C01_PG_URL} must be set for disposable PG tests")
    # Harness must not silently fall back to DATABASE_URL.
    general = os.environ.get(_GENERAL_DATABASE_URL, "").strip()
    if general and cleaned == general:
        raise ValueError(
            "disposable URL must not equal general DATABASE_URL; use dedicated opt-in variable"
        )
    return _validate_parsed_disposable_url(cleaned)


def validated_disposable_pg_url() -> str:
    return parse_disposable_pg_url(os.environ.get(C01_PG_URL, ""), require_opt_in=True)