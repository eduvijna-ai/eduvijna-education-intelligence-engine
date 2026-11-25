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
_OWNED_DB_PREFIX = "c01_at_"
_ADMIN_DATABASES = frozenset({"postgres"})
_OWNED_DATABASE_REGISTRY: set[str] = set()


def register_owned_database(database_name: str) -> None:
    if not database_name.startswith(_OWNED_DB_PREFIX):
        raise ValueError(f"owned database name must start with {_OWNED_DB_PREFIX!r}")
    _OWNED_DATABASE_REGISTRY.add(database_name)


def assert_owned_database_registered(database_name: str) -> None:
    if database_name not in _OWNED_DATABASE_REGISTRY:
        raise ValueError(f"database {database_name!r} is not in this run ownership registry")


def clear_owned_database_registry() -> None:
    _OWNED_DATABASE_REGISTRY.clear()


def _validate_parsed_disposable_url(raw: str, *, require_registry: bool = True) -> str:
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
    database_name = parsed.path.lstrip("/")
    if database_name not in _ADMIN_DATABASES:
        if not database_name.startswith(_OWNED_DB_PREFIX):
            raise ValueError(
                f"database {database_name!r} must use owned prefix {_OWNED_DB_PREFIX}"
            )
        if require_registry:
            assert_owned_database_registered(database_name)
    return raw


def _validate_cluster_url(raw: str) -> str:
    parsed = urlparse(raw.strip())
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
    return raw.strip()


def validated_disposable_pg_cluster() -> str:
    if os.environ.get(C01_PG_OPT_IN) != "1":
        raise ValueError(f"{C01_PG_OPT_IN}=1 required")
    raw = os.environ.get(C01_PG_URL, "").strip()
    if not raw:
        raise ValueError(f"{C01_PG_URL} must be set for disposable PG tests")
    return _validate_cluster_url(raw)


def parse_disposable_pg_url(
    raw: str, *, require_opt_in: bool = True, require_registry: bool = True
) -> str:
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
    return _validate_parsed_disposable_url(cleaned, require_registry=require_registry)


def validated_disposable_pg_url() -> str:
    return parse_disposable_pg_url(
        os.environ.get(C01_PG_URL, ""),
        require_opt_in=True,
        require_registry=True,
    )