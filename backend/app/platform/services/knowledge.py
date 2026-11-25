from __future__ import annotations

from app.platform.auth.principal import RequestPrincipal
from app.platform.auth.rbac import require_permission
from app.platform.capability_registry import get_capability
from app.platform.errors import CapabilityNotReadyError


def search_knowledge(
    *,
    principal: RequestPrincipal,
    query: str,
    limit: int,
) -> None:
    _ = query
    _ = limit
    require_permission(principal.scopes, "knowledge:read")
    cap = get_capability("knowledge.search")
    if cap is None:
        raise CapabilityNotReadyError(capability="knowledge.search", reason="Unknown")
    raise CapabilityNotReadyError(capability="knowledge.search", reason=cap.reason)