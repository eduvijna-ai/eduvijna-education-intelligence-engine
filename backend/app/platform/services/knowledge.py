from __future__ import annotations

from app.platform.auth.principal import RequestPrincipal
from app.platform.auth.rbac import require_permission
from app.platform.capability_registry import assert_capability_operable
from app.platform.schemas.endpoints import KnowledgeSearchHit, KnowledgeSearchResponse


def search_knowledge(
    *,
    principal: RequestPrincipal,
    query: str,
    limit: int,
) -> KnowledgeSearchResponse:
    assert_capability_operable("knowledge.search")
    require_permission(principal.scopes, "knowledge:read")
    # Structural response without provider calls when no indexed corpus bound.
    return KnowledgeSearchResponse(
        hits=[
            KnowledgeSearchHit(
                snippet="Knowledge search contract active; no live corpus in this candidate.",
                source_ref="contract-only",
                provenance={
                    "tenant": principal.organization_id,
                    "mode": "fail_closed_empty",
                },
            )
        ][:limit],
        query=query,
    )
