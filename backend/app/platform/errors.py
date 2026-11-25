from __future__ import annotations

from app.core.errors import AppError


class AuthenticationError(AppError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(code="AUTHENTICATION_ERROR", message=message, status_code=401)


class AuthorizationError(AppError):
    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(code="AUTHORIZATION_ERROR", message=message, status_code=403)


class CapabilityNotReadyError(AppError):
    def __init__(self, *, capability: str, reason: str) -> None:
        super().__init__(
            code="CAPABILITY_NOT_READY",
            message=f"Capability '{capability}' is not ready: {reason}",
            status_code=503,
        )


class ConflictError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(code="CONFLICT", message=message, status_code=409)


class DependencyUnavailableError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(code="DEPENDENCY_UNAVAILABLE", message=message, status_code=503)


class NotFoundError(AppError):
    def __init__(self, message: str = "Not found") -> None:
        super().__init__(code="NOT_FOUND", message=message, status_code=404)


class RateLimitError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="RATE_LIMIT_EXCEEDED",
            message="Rate limit exceeded",
            status_code=429,
        )
