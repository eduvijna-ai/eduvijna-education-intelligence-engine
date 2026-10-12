from __future__ import annotations

from dataclasses import dataclass

from app.knowledge_intelligence.enums import KnowledgeOwnershipScope
from app.models.enums import SourceTrustTier
from app.models.source import Source


@dataclass(frozen=True, slots=True)
class KnowledgeScope:
    ownership_scope: KnowledgeOwnershipScope
    organization_id: str | None
    institution_id: str | None
    teacher_id: str | None


def scope_from_source(source: Source) -> KnowledgeScope:
    if source.teacher_id:
        return KnowledgeScope(
            ownership_scope=KnowledgeOwnershipScope.TEACHER,
            organization_id=source.organization_id,
            institution_id=source.institution_id,
            teacher_id=source.teacher_id,
        )
    if source.institution_id:
        return KnowledgeScope(
            ownership_scope=KnowledgeOwnershipScope.INSTITUTION,
            organization_id=source.organization_id,
            institution_id=source.institution_id,
            teacher_id=None,
        )
    if source.organization_id:
        return KnowledgeScope(
            ownership_scope=KnowledgeOwnershipScope.ORGANIZATION,
            organization_id=source.organization_id,
            institution_id=None,
            teacher_id=None,
        )
    return KnowledgeScope(
        ownership_scope=KnowledgeOwnershipScope.GLOBAL_OFFICIAL,
        organization_id=None,
        institution_id=None,
        teacher_id=None,
    )


def authority_label_for_source(source: Source) -> str:
    tier = SourceTrustTier(source.trust_tier)
    if tier in {SourceTrustTier.OFFICIAL_PRIMARY, SourceTrustTier.OFFICIAL_SUPPORTING}:
        return "official_source"
    if tier == SourceTrustTier.INSTITUTION:
        return "institution_evidence"
    if tier == SourceTrustTier.TEACHER:
        return "teacher_evidence"
    return "analytical_evidence"


def is_official_source_type(source_type: str) -> bool:
    return source_type in Source.official_type_values()


def tenant_scope_matches(
    binding_scope: KnowledgeScope,
    request_org: str | None,
    request_inst: str | None,
    request_teacher: str | None,
) -> bool:
    if binding_scope.ownership_scope == KnowledgeOwnershipScope.GLOBAL_OFFICIAL:
        return True
    if binding_scope.ownership_scope == KnowledgeOwnershipScope.ORGANIZATION:
        return request_org == binding_scope.organization_id
    if binding_scope.ownership_scope == KnowledgeOwnershipScope.INSTITUTION:
        return (
            request_org == binding_scope.organization_id
            and request_inst == binding_scope.institution_id
        )
    if binding_scope.ownership_scope == KnowledgeOwnershipScope.TEACHER:
        return (
            request_org == binding_scope.organization_id
            and request_inst == binding_scope.institution_id
            and request_teacher == binding_scope.teacher_id
        )
    return False


def binding_visible_to_request(
    binding_scope: KnowledgeScope,
    *,
    organization_id: str | None,
    institution_id: str | None,
    teacher_id: str | None,
) -> bool:
    if binding_scope.ownership_scope == KnowledgeOwnershipScope.GLOBAL_OFFICIAL:
        return True
    if organization_id is None and institution_id is None and teacher_id is None:
        return False
    return tenant_scope_matches(binding_scope, organization_id, institution_id, teacher_id)
