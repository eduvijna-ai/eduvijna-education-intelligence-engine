"""Strict exact-type validation — internal / detached DTO helpers only."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from pydantic import BaseModel

from app.adaptive_remediation.contracts import EvidenceObservation


def exact_type(value: object, expected: type[object]) -> bool:
    return type(value) is expected


def require_exact_observation_tuple(
    observations: object,
) -> tuple[EvidenceObservation, ...] | None:
    if not exact_type(observations, tuple):
        return None
    obs_tuple = cast(tuple[object, ...], observations)
    for item in obs_tuple:
        if not exact_type(item, EvidenceObservation):
            return None
    return cast(tuple[EvidenceObservation, ...], observations)


def reject_unsafe_value(value: object) -> tuple[bool, str | None]:
    if exact_type(value, bool):
        return False, "BOOL_NOT_VALID_INT"
    if exact_type(value, float):
        return False, "FLOAT_NOT_VALID_INT"
    if exact_type(value, str) or exact_type(value, bytes) or exact_type(value, bytearray):
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


def require_strict_positive_int(value: object) -> int | None:
    if not exact_type(value, int):
        return None
    as_int = cast(int, value)
    if as_int <= 0:
        return None
    return as_int


def require_exact_model(value: object, model_type: type[BaseModel]) -> BaseModel | None:
    if type(value) is not model_type:
        return None
    return value