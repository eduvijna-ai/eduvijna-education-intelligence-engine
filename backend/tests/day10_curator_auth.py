from __future__ import annotations

import secrets

from sqlalchemy.orm import Session

from app.curator_auth.issuer import (
    CuratorScope,
    issue_curator_write_decision,
    provision_operator_credential,
)
from app.curator_auth.roles import CuratorOperation, CuratorRole
from app.models.policy import PolicyRule
from app.models.tenancy import AdminActor
from app.paper_distribution.mandatory_policy_claim_authority import (
    curator_scope_for_policy_rule,
    mandatory_policy_approve_binding_payload,
)
from app.root_cause_intelligence.mapping_claim_authority import (
    MappingClaimApprovalContext,
    curator_scope_from_mapping_context,
    mapping_approve_binding_payload,
    mapping_revoke_binding_payload,
)
from app.root_cause_intelligence.mapping_registry import MisconceptionConceptMapping

DEFAULT_MAPPING_CURATOR_SECRET = secrets.token_hex(24)
DEFAULT_POLICY_CURATOR_SECRET = secrets.token_hex(24)


def test_curator_signing_key() -> str:
    return secrets.token_hex(32)


def ensure_mapping_curator_credential(
    session: Session,
    admin: AdminActor,
    *,
    organization_id: str,
    institution_id: str,
    curriculum_version_id: str,
    operator_secret: str = DEFAULT_MAPPING_CURATOR_SECRET,
) -> None:
    scope = CuratorScope(
        organization_id=organization_id,
        institution_id=institution_id,
        curriculum_version_id=curriculum_version_id,
    )
    provision_operator_credential(
        session,
        admin_actor=admin,
        role=CuratorRole.MAPPING_CURATOR,
        operator_secret=operator_secret,
        scope=scope,
    )


def ensure_mandatory_policy_curator_credential(
    session: Session,
    admin: AdminActor,
    *,
    organization_id: str,
    institution_id: str,
    operator_secret: str = DEFAULT_POLICY_CURATOR_SECRET,
    board_code: str | None = None,
    teacher_id: str | None = None,
) -> None:
    scope = CuratorScope(
        organization_id=organization_id,
        institution_id=institution_id,
        board_code=board_code,
        teacher_id=teacher_id,
    )
    provision_operator_credential(
        session,
        admin_actor=admin,
        role=CuratorRole.MANDATORY_POLICY_CURATOR,
        operator_secret=operator_secret,
        scope=scope,
    )


def issue_mapping_approve_decision(
    session: Session,
    *,
    admin_external_code: str,
    operator_secret: str,
    approval_context: MappingClaimApprovalContext,
    revision_id: str,
    entry: MisconceptionConceptMapping,
    source_locator: str,
    mapping_registry_version: str,
) -> str:
    scope = curator_scope_from_mapping_context(approval_context)
    binding = mapping_approve_binding_payload(
        revision_id=revision_id,
        entry=entry,
        source_locator=source_locator,
        mapping_registry_version=mapping_registry_version,
        approval_context=approval_context,
    )
    return issue_curator_write_decision(
        session,
        admin_external_code=admin_external_code,
        operator_secret=operator_secret,
        role=CuratorRole.MAPPING_CURATOR,
        operation=CuratorOperation.MAPPING_APPROVE,
        binding_payload=binding,
        scope=scope,
    )


def issue_mapping_revoke_decision(
    session: Session,
    *,
    admin_external_code: str,
    operator_secret: str,
    approval_context: MappingClaimApprovalContext,
    revision_id: str,
    claim_id: str,
) -> str:
    scope = curator_scope_from_mapping_context(approval_context)
    binding = mapping_revoke_binding_payload(revision_id=revision_id, claim_id=claim_id)
    return issue_curator_write_decision(
        session,
        admin_external_code=admin_external_code,
        operator_secret=operator_secret,
        role=CuratorRole.MAPPING_CURATOR,
        operation=CuratorOperation.MAPPING_REVOKE,
        binding_payload=binding,
        scope=scope,
    )


def issue_mandatory_policy_approve_decision(
    session: Session,
    *,
    admin_external_code: str,
    operator_secret: str,
    organization_id: str,
    institution_id: str,
    rule: PolicyRule,
    revision_id: str,
    value_checksum: str,
    rule_lifecycle_digest: str,
) -> str:
    scope = curator_scope_for_policy_rule(
        rule, organization_id=organization_id, institution_id=institution_id
    )
    binding = mandatory_policy_approve_binding_payload(
        rule_id=str(rule.id),
        revision_id=revision_id,
        scope_type=str(rule.scope_type),
        scope_code=str(rule.scope_code),
        policy_key=str(rule.policy_key),
        value_checksum=value_checksum,
        rule_lifecycle_digest=rule_lifecycle_digest,
    )
    return issue_curator_write_decision(
        session,
        admin_external_code=admin_external_code,
        operator_secret=operator_secret,
        role=CuratorRole.MANDATORY_POLICY_CURATOR,
        operation=CuratorOperation.MANDATORY_POLICY_APPROVE,
        binding_payload=binding,
        scope=scope,
    )


def approve_mapping_with_curator(
    session: Session,
    *,
    revision_id: str,
    entry: MisconceptionConceptMapping,
    source_locator: str,
    mapping_registry_version: str,
    approval_context: MappingClaimApprovalContext,
    admin_external_code: str | None = None,
    operator_secret: str = DEFAULT_MAPPING_CURATOR_SECRET,
    storage_root: str | None = None,
    request_id: str | None = None,
) -> str:
    from app.root_cause_intelligence.mapping_claim_authority import (
        approve_root_cause_mapping_claim,
    )

    actor_code = admin_external_code or str(approval_context.actor_id)
    token = issue_mapping_approve_decision(
        session,
        admin_external_code=actor_code,
        operator_secret=operator_secret,
        approval_context=approval_context,
        revision_id=revision_id,
        entry=entry,
        source_locator=source_locator,
        mapping_registry_version=mapping_registry_version,
    )
    return approve_root_cause_mapping_claim(
        session,
        revision_id=revision_id,
        entry=entry,
        source_locator=source_locator,
        mapping_registry_version=mapping_registry_version,
        approval_context=approval_context,
        curator_decision_token=token,
        request_id=request_id,
        storage_root=storage_root,
    )


def approve_mandatory_policy_with_curator(
    session: Session,
    *,
    rule: PolicyRule,
    revision_id: str,
    organization_id: str,
    institution_id: str,
    actor_id: str,
    policy_curator_secret: str = DEFAULT_POLICY_CURATOR_SECRET,
) -> str:
    from app.paper_distribution.mandatory_policy_claim_authority import (
        _policy_value_checksum,
        _rule_lifecycle_digest,
        approve_mandatory_policy_claim,
    )

    value_checksum = _policy_value_checksum(dict(rule.value_json or {}))
    lifecycle = _rule_lifecycle_digest(rule)
    token = issue_mandatory_policy_approve_decision(
        session,
        admin_external_code=actor_id,
        operator_secret=policy_curator_secret,
        organization_id=organization_id,
        institution_id=institution_id,
        rule=rule,
        revision_id=revision_id,
        value_checksum=value_checksum,
        rule_lifecycle_digest=lifecycle,
    )
    return approve_mandatory_policy_claim(
        session,
        rule_id=str(rule.id),
        revision_id=revision_id,
        scope_type=str(rule.scope_type),
        scope_code=str(rule.scope_code),
        policy_key=str(rule.policy_key),
        value_json=dict(rule.value_json or {}),
        actor_id=actor_id,
        organization_id=organization_id,
        institution_id=institution_id,
        curator_decision_token=token,
    )
