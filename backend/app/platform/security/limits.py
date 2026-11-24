"""D17-13 request size and single-process rate limiting."""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request

from app.core.config import get_settings
from app.platform.errors import RateLimitError

_MAX_BODY_BYTES = 2 * 1024 * 1024
_WINDOW_SECONDS = 60
_MAX_REQUESTS_PER_WINDOW = 120

_buckets: dict[str, list[float]] = defaultdict(list)
_DISTRIBUTED_RATE_LIMIT = False


async def request_size_limit_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > _MAX_BODY_BYTES:
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "PAYLOAD_TOO_LARGE",
                            "message": "Request body too large",
                            "request_id": getattr(request.state, "request_id", "unknown"),
                        }
                    },
                )
        except ValueError:
            pass
    return await call_next(request)


async def rate_limit_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    if request.url.path in {"/health", "/ready"}:
        return await call_next(request)
    client_key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _buckets[client_key]
    cutoff = now - _WINDOW_SECONDS
    _buckets[client_key] = [t for t in window if t >= cutoff]
    if len(_buckets[client_key]) >= _MAX_REQUESTS_PER_WINDOW:
        raise RateLimitError()
    _buckets[client_key].append(now)
    response = await call_next(request)
    response.headers["X-RateLimit-Distributed"] = str(_DISTRIBUTED_RATE_LIMIT).lower()
    response.headers["X-RateLimit-Policy"] = (
        f"local-process:{_MAX_REQUESTS_PER_WINDOW}/{_WINDOW_SECONDS}s"
    )
    return response


def security_limits_snapshot() -> dict[str, object]:
    _ = get_settings()
    return {
        "max_body_bytes": _MAX_BODY_BYTES,
        "rate_limit_distributed": _DISTRIBUTED_RATE_LIMIT,
        "rate_limit_local": f"{_MAX_REQUESTS_PER_WINDOW}/{_WINDOW_SECONDS}s",
    }
