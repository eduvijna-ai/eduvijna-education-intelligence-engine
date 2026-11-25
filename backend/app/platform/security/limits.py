"""D17-13 request size and single-process rate limiting."""

from __future__ import annotations

import time
from collections import OrderedDict

from fastapi import Request
from starlette.responses import JSONResponse

from app.core.config import get_settings

_MAX_BODY_BYTES = 2 * 1024 * 1024
_WINDOW_SECONDS = 60
_MAX_REQUESTS_PER_WINDOW = 120
_MAX_CLIENT_BUCKETS = 10_000
_DISTRIBUTED_RATE_LIMIT = False

_buckets: OrderedDict[str, list[float]] = OrderedDict()

_BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _error_response(request: Request, *, status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", "unknown"),
            }
        },
    )


async def request_size_limit_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    if request.method not in _BODY_METHODS:
        return await call_next(request)

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            return _error_response(
                request,
                status_code=413,
                code="PAYLOAD_TOO_LARGE",
                message="Invalid Content-Length header",
            )
        if declared > _MAX_BODY_BYTES:
            return _error_response(
                request,
                status_code=413,
                code="PAYLOAD_TOO_LARGE",
                message="Request body too large",
            )

    total = 0
    original_receive = request.receive

    async def bounded_receive():  # type: ignore[no-untyped-def]
        nonlocal total
        message = await original_receive()
        if message["type"] == "http.request":
            total += len(message.get("body", b""))
            if total > _MAX_BODY_BYTES:
                return {"type": "http.disconnect"}
        return message

    request._receive = bounded_receive
    response = await call_next(request)
    if total > _MAX_BODY_BYTES:
        return _error_response(
            request,
            status_code=413,
            code="PAYLOAD_TOO_LARGE",
            message="Request body too large",
        )
    return response


async def rate_limit_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    if request.url.path in {"/health", "/ready"}:
        return await call_next(request)
    client_key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _buckets.get(client_key, [])
    cutoff = now - _WINDOW_SECONDS
    window = [t for t in window if t >= cutoff]
    if len(window) >= _MAX_REQUESTS_PER_WINDOW:
        return _error_response(
            request,
            status_code=429,
            code="RATE_LIMIT_EXCEEDED",
            message="Rate limit exceeded",
        )
    window.append(now)
    _buckets[client_key] = window
    _buckets.move_to_end(client_key)
    while len(_buckets) > _MAX_CLIENT_BUCKETS:
        _buckets.popitem(last=False)
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
        "max_client_buckets": _MAX_CLIENT_BUCKETS,
        "body_read_mode": "bounded_receive_wrapper",
    }