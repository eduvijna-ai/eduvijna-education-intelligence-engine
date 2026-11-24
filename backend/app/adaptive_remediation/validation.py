"""Strict type validation before pure-helper attribute access."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel


def reject_unsafe_value(value: object) -> tuple[bool, str | None]:
    if isinstance(value, (bool,)):
        return False, "BOOL_NOT_VALID_INT"
    if isinstance(value, (float,)):
        return False, "FLOAT_NOT_VALID_INT"
    if isinstance(value, (str, bytes, bytearray)):
        return False, "RAW_STRING_INPUT_BLOCKED"
    if _looks_like_orm(value):
        return False, "ORM_INSTANCE_BLOCKED"
    module = getattr(type(value), "__module__", "") or ""
    qualname = getattr(type(value), "__qualname__", "") or ""
    if "Session" in qualname or module.startswith("sqlalchemy"):
        return False, "SESSION_BLOCKED"
    if isinstance(value, Mapping):
        for _k, v in value.items():
            ok, code = reject_unsafe_value(v)
            if not ok:
                return False, code or "NESTED_UNSAFE"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            ok, code = reject_unsafe_value(item)
            if not ok:
                return False, code or "NESTED_UNSAFE"
    return True, None


def _looks_like_orm(value: object) -> bool:
    module = getattr(type(value), "__module__", "") or ""
    return module.startswith("app.models.")


def require_positive_int(value: object, *, field: str) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value <= 0:
        return None
    return value


def require_validated_model(value: object, model_type: type[BaseModel]) -> BaseModel | None:
    if not isinstance(value, model_type):
        return None
    return value
