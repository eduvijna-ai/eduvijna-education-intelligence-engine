from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import Request, Response

logger = logging.getLogger("eduvijna.http")

_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:access_token|api_key|apikey|key|token|secret|password)=)[^&\s]+"
)
_AUTH_SECRET_RE = re.compile(
    r"(?i)(authorization:\s*(?:bearer|basic)\s+)[^\s]+"
)


def redact_log_text(value: str) -> str:
    value = _QUERY_SECRET_RE.sub(r"\1[REDACTED]", value)
    return _AUTH_SECRET_RE.sub(r"\1[REDACTED]", value)


class SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = redact_log_text(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
    )
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(item, SecretRedactionFilter) for item in handler.filters):
            handler.addFilter(SecretRedactionFilter())

    # Dependency request logs can include complete URLs. Keep them out of INFO output.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["x-request-id"] = request_id
        return response
    finally:
        event: dict[str, Any] = {
            "event": "http_request",
            "timestamp": datetime.now(UTC).isoformat(),
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": status,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        logger.info(json.dumps(event, separators=(",", ":")))
