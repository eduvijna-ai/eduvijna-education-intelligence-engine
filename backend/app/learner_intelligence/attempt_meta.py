from __future__ import annotations

from app.models.learner_intelligence import AssessmentAttempt

_BIND_KEY = "harness_binding_secret"
_CATALOG_KEY = "catalog_key"


def harness_binding_from_attempt(attempt: AssessmentAttempt) -> str | None:
    meta = attempt.metadata_json if isinstance(attempt.metadata_json, dict) else {}
    value = meta.get(_BIND_KEY)
    return str(value) if value else None


def catalog_key_from_attempt(attempt: AssessmentAttempt) -> str:
    meta = attempt.metadata_json if isinstance(attempt.metadata_json, dict) else {}
    return str(meta.get(_CATALOG_KEY) or "")