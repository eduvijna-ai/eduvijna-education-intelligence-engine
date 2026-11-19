"""JEE Advanced 2026 reference source curator identity (fail-closed; no string allowlists)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.education_intelligence import PolicyRegistryEntry
from app.models.tenancy import AdminActor

JEE_ADVANCED_SOURCE_CURATORS_KEY = "jee_advanced_source_curators"
JEE_ADVANCED_SOURCE_CURATORS_VERSION = "jee-advanced-source-curators@v1"


def authorized_source_curator_verified(session: Session, actor_id: str | None) -> bool:
    """True when actor_id is an active AdminActor listed in the source-curator policy registry."""
    if not actor_id or not str(actor_id).strip():
        return False
    normalized = str(actor_id).strip()
    registry = session.scalar(
        select(PolicyRegistryEntry).where(
            PolicyRegistryEntry.registry_key == JEE_ADVANCED_SOURCE_CURATORS_KEY,
            PolicyRegistryEntry.version == JEE_ADVANCED_SOURCE_CURATORS_VERSION,
            PolicyRegistryEntry.status == "active",
        )
    )
    if registry is None:
        return False
    allowed = registry.payload_json.get("actor_ids") or []
    if not isinstance(allowed, list):
        return False
    if normalized not in {str(item).strip() for item in allowed if item}:
        return False
    admin = session.scalar(
        select(AdminActor).where(
            AdminActor.external_code == normalized,
            AdminActor.active.is_(True),
        )
    )
    return admin is not None