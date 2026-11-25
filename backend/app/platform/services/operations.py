from __future__ import annotations

from app.platform.capability_registry import containment_snapshot
from app.platform.security.limits import security_limits_snapshot


def build_operations_status() -> dict[str, object]:
    return {
        "status": "ok",
        "readiness": "degraded",
        "containment": containment_snapshot(),
        "limits": security_limits_snapshot(),
        "provider_calls_on_blocked_paths": False,
    }
