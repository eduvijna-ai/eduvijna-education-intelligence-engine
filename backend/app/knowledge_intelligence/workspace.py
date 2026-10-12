from __future__ import annotations

import hashlib

from app.adapters.anythingllm.types import WorkspaceKey
from app.knowledge_intelligence.enums import KnowledgeOwnershipScope
from app.knowledge_intelligence.scope import KnowledgeScope


def workspace_key_for_scope(scope: KnowledgeScope) -> WorkspaceKey:
    parts: list[str] = [scope.ownership_scope.value]
    if scope.organization_id:
        parts.append(f"org:{scope.organization_id}")
    if scope.institution_id:
        parts.append(f"inst:{scope.institution_id}")
    if scope.teacher_id:
        parts.append(f"teacher:{scope.teacher_id}")
    scope_key = "|".join(parts)
    digest = hashlib.sha256(scope_key.encode()).hexdigest()[:16]
    slug = f"eduvijna-{digest}"
    return WorkspaceKey(scope_key=scope_key, slug=slug)


def workspace_key_from_parts(
    ownership_scope: KnowledgeOwnershipScope,
    organization_id: str | None,
    institution_id: str | None,
    teacher_id: str | None,
) -> WorkspaceKey:
    return workspace_key_for_scope(
        KnowledgeScope(
            ownership_scope=ownership_scope,
            organization_id=organization_id,
            institution_id=institution_id,
            teacher_id=teacher_id,
        )
    )
