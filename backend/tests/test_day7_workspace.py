from __future__ import annotations

from app.knowledge_intelligence.enums import KnowledgeOwnershipScope
from app.knowledge_intelligence.scope import KnowledgeScope
from app.knowledge_intelligence.workspace import workspace_key_for_scope


def test_profile_versions_produce_distinct_workspace_slugs() -> None:
    scope = KnowledgeScope(
        ownership_scope=KnowledgeOwnershipScope.GLOBAL_OFFICIAL,
        organization_id=None,
        institution_id=None,
        teacher_id=None,
    )
    v0 = workspace_key_for_scope(scope, retrieval_profile_version="ki-retrieval-v0")
    v1 = workspace_key_for_scope(scope, retrieval_profile_version="ki-retrieval-v1")
    assert v0.slug != v1.slug
    assert "profile:ki-retrieval-v0" in v0.scope_key
    assert "profile:ki-retrieval-v1" in v1.scope_key
