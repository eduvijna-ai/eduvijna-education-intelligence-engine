from __future__ import annotations


class IdempotencyConflictError(Exception):
    """Same idempotency key was reused with a different request payload."""

    def __init__(self, idempotency_key: str, message: str = "idempotency_key_conflict") -> None:
        super().__init__(message)
        self.idempotency_key = idempotency_key
        self.code = message


class OrchestrationConfigurationError(Exception):
    """Production orchestration is not configured (fail closed)."""
