from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantContext:
    organization_id: str = "local-org"
    institution_id: str = "local-institution"
    actor_id: str = "local-actor"
