from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import PolicyScopeType, SourceRevisionStatus, SourceStatus
from app.models.policy import PolicyRule
from app.models.source import SourceAuditEvent, SourceRevision, policy_rule_source_revisions
from app.models.tenancy import Institution, Organization, Teacher
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.mandatory_policy_claim_authority import (
    mandatory_policy_claim_active,
    mandatory_policy_enforcement_obligation_active,
    mandatory_policy_historic_rule_ids_for_execution,
    mandatory_policy_signed_rule_retirement_recorded,
)
from app.source_intelligence.approval_fingerprint import compute_revision_approval_fingerprint

PAPER_MANDATORY_POLICY_KEY = "paper_distribution_mandatory_targets"

_SCOPE_PRECEDENCE = {
    PolicyScopeType.BOARD.value: 300,
    PolicyScopeType.INSTITUTION.value: 200,
    PolicyScopeType.TEACHER.value: 100,
}


def resolve_institution_board_code(session: Session, institution_id: str | None) -> str | None:
    if not institution_id:
        return None
    institution = session.get(Institution, institution_id)
    if institution is None:
        return None
    board_code = (institution.metadata_json or {}).get("board_code")
    return str(board_code).strip() if board_code else None


def mandatory_policy_context_errors(
    session: Session,
    execution_context: PaperExecutionContext | None,
) -> list[str]:
    if execution_context is None or not execution_context.institution_id:
        return []
    institution = session.get(Institution, execution_context.institution_id)
    if institution is None:
        return ["execution_context.institution_id"]
    if not institution.active:
        return ["execution_context.institution_id"]
    organization = session.get(Organization, institution.organization_id)
    if organization is None or not organization.active:
        return ["execution_context.organization_id"]
    board_code = resolve_institution_board_code(session, execution_context.institution_id)
    if execution_context.organization_id:
        if str(institution.organization_id) != str(execution_context.organization_id):
            return ["execution_context.organization_id"]
        scoped_org = session.get(Organization, execution_context.organization_id)
        if scoped_org is None or not scoped_org.active:
            return ["execution_context.organization_id"]
    if execution_context.board_code:
        if not board_code:
            return ["execution_context.board_code"]
        if execution_context.board_code != board_code:
            return ["execution_context.board_code"]
    if execution_context.teacher_id:
        teacher = session.get(Teacher, execution_context.teacher_id)
        if teacher is None or teacher.institution_id != execution_context.institution_id:
            return ["execution_context.teacher_id"]
        if not teacher.active:
            return ["execution_context.teacher_id"]
    return []


def _rule_covers_scope(
    rule: PolicyRule,
    *,
    board_code: str | None,
    institution: Institution | None,
    teacher_id: str | None,
) -> bool:
    scope_type = str(rule.scope_type)
    scope_code = str(rule.scope_code)
    if scope_type == PolicyScopeType.BOARD.value:
        return bool(board_code and scope_code == board_code)
    if scope_type == PolicyScopeType.INSTITUTION.value and institution is not None:
        return scope_code in {institution.id, institution.code}
    if scope_type == PolicyScopeType.TEACHER.value:
        return bool(teacher_id and scope_code == teacher_id)
    return False


def _latest_source_approved_audit(
    session: Session, revision_id: str
) -> SourceAuditEvent | None:
    return session.scalar(
        select(SourceAuditEvent)
        .where(
            SourceAuditEvent.source_revision_id == revision_id,
            SourceAuditEvent.event_type == "source_approved",
            SourceAuditEvent.outcome == "success",
        )
        .order_by(SourceAuditEvent.created_at.desc())
    )


def _revision_authorized_for_policy(
    session: Session,
    rule: PolicyRule,
    execution_context: PaperExecutionContext | None,
) -> bool:
    revision_ids: list[str] = list(
        session.scalars(
            select(policy_rule_source_revisions.c.source_revision_id).where(
                policy_rule_source_revisions.c.policy_rule_id == rule.id
            )
        ).all()
    )
    if not revision_ids:
        return False
    for revision_id in revision_ids:
        revision = session.get(SourceRevision, str(revision_id))
        if revision is None or revision.source is None:
            return False
        source = revision.source
        if source.status != SourceStatus.ACTIVE.value:
            return False
        if revision.status != SourceRevisionStatus.ACTIVE.value:
            return False
        if not revision.approval_fingerprint or not revision.approved_by:
            return False
        approved = _latest_source_approved_audit(session, str(revision_id))
        if approved is None:
            return False
        audit_fingerprint = str(
            (approved.payload_json or {}).get("approval_fingerprint") or ""
        )
        if audit_fingerprint != str(revision.approval_fingerprint):
            return False
        if compute_revision_approval_fingerprint(session, revision) != str(
            revision.approval_fingerprint
        ):
            return False
        org_id = ""
        inst_id = ""
        if execution_context is not None:
            org_id = str(execution_context.organization_id or "").strip()
            inst_id = str(execution_context.institution_id or "").strip()
            if not org_id and inst_id:
                institution = session.get(Institution, inst_id)
                if institution is not None:
                    org_id = str(institution.organization_id)
        if not mandatory_policy_claim_active(
            session,
            rule_id=str(rule.id),
            revision_id=str(revision_id),
            scope_type=str(rule.scope_type),
            scope_code=str(rule.scope_code),
            policy_key=str(rule.policy_key),
            value_json=dict(rule.value_json or {}),
            organization_id=org_id,
            institution_id=inst_id,
            execution_context=execution_context,
        ):
            return False
    return True


def _scoped_mandatory_rule_candidates(
    session: Session,
    *,
    board_code: str | None,
    institution: Institution | None,
    teacher_id: str | None,
    on_date: date | None = None,
    active_only: bool = True,
) -> list[PolicyRule]:
    effective = on_date or date.today()
    rules = session.scalars(
        select(PolicyRule).where(
            PolicyRule.policy_key == PAPER_MANDATORY_POLICY_KEY,
        )
    ).all()
    candidates: list[PolicyRule] = []
    for rule in rules:
        if active_only and not rule.active:
            continue
        if rule.effective_from is not None and rule.effective_from > effective:
            continue
        if rule.effective_to is not None and rule.effective_to < effective:
            continue
        if not _rule_covers_scope(
            rule,
            board_code=board_code,
            institution=institution,
            teacher_id=teacher_id,
        ):
            continue
        candidates.append(rule)
    return candidates


def _scoped_active_mandatory_rule_candidates(
    session: Session,
    *,
    board_code: str | None,
    institution: Institution | None,
    teacher_id: str | None,
    on_date: date | None = None,
) -> list[PolicyRule]:
    return _scoped_mandatory_rule_candidates(
        session,
        board_code=board_code,
        institution=institution,
        teacher_id=teacher_id,
        on_date=on_date,
        active_only=True,
    )


def _resolve_authorized_mandatory_rules(
    session: Session,
    *,
    board_code: str | None,
    institution: Institution | None,
    teacher_id: str | None,
    execution_context: PaperExecutionContext | None,
    on_date: date | None = None,
) -> tuple[list[PolicyRule], list[str]]:
    effective = on_date or date.today()
    active_candidates = _scoped_active_mandatory_rule_candidates(
        session,
        board_code=board_code,
        institution=institution,
        teacher_id=teacher_id,
        on_date=effective,
    )
    obligation_scope = _scoped_mandatory_rule_candidates(
        session,
        board_code=board_code,
        institution=institution,
        teacher_id=teacher_id,
        on_date=effective,
        active_only=False,
    )
    historic_rule_ids = mandatory_policy_historic_rule_ids_for_execution(
        session,
        board_code=board_code,
        institution=institution,
        teacher_id=teacher_id,
        on_date=effective,
    )
    selected: list[PolicyRule] = []
    auth_errors: list[str] = []
    seen_rule_ids: set[str] = set()
    candidate_rules: list[PolicyRule] = list(active_candidates)
    for rule in obligation_scope:
        if rule.id not in {item.id for item in candidate_rules}:
            candidate_rules.append(rule)
    for rule_id in historic_rule_ids:
        if rule_id in seen_rule_ids:
            continue
        extra = session.get(PolicyRule, rule_id)
        if extra is not None and extra.id not in {item.id for item in candidate_rules}:
            candidate_rules.append(extra)
    for rule in candidate_rules:
        seen_rule_ids.add(str(rule.id))
        if rule.active and _revision_authorized_for_policy(
            session, rule, execution_context
        ):
            selected.append(rule)
            continue
        if not mandatory_policy_enforcement_obligation_active(
            session,
            rule,
            board_code=board_code,
            institution=institution,
            teacher_id=teacher_id,
            on_date=effective,
        ):
            continue
        if not rule.active:
            if mandatory_policy_signed_rule_retirement_recorded(session, rule):
                continue
            auth_errors.append(f"mandatory_policy.retirement_unauthorized:{rule.id}")
            continue
        auth_errors.append(f"mandatory_policy.authorization_unavailable:{rule.id}")
    deduped_errors = list(dict.fromkeys(auth_errors))
    return (
        sorted(
            selected,
            key=lambda item: (
                -_SCOPE_PRECEDENCE.get(str(item.scope_type), 0),
                -item.priority,
            ),
        ),
        deduped_errors,
    )


def _active_rules_for_context(
    session: Session,
    *,
    board_code: str | None,
    institution: Institution | None,
    teacher_id: str | None,
    execution_context: PaperExecutionContext | None,
    on_date: date | None = None,
) -> list[PolicyRule]:
    rules, _ = _resolve_authorized_mandatory_rules(
        session,
        board_code=board_code,
        institution=institution,
        teacher_id=teacher_id,
        execution_context=execution_context,
        on_date=on_date,
    )
    return rules


def _merge_mandatory_entry(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any],
    *,
    incoming_precedence: int,
    existing_precedence: int,
) -> tuple[dict[str, Any], str | None]:
    key = str(incoming.get("key") or (existing.get("key") if existing else "") or "")
    merged = dict(existing or {"key": key})
    for field in ("exact_count", "exact_percent"):
        new_val = incoming.get(field)
        old_val = merged.get(field)
        if new_val is None:
            continue
        if old_val is not None and float(old_val) != float(new_val):
            return merged, f"mandatory.{key}.{field}"
        merged[field] = new_val
    for field in ("min_percent", "max_percent"):
        new_val = incoming.get(field)
        if new_val is None:
            continue
        old_val = merged.get(field)
        if field == "min_percent" and old_val is not None:
            if incoming_precedence >= existing_precedence:
                merged[field] = max(float(old_val), float(new_val))
            else:
                merged[field] = max(float(old_val), float(new_val))
        elif field == "max_percent" and old_val is not None:
            merged[field] = min(float(old_val), float(new_val))
        else:
            merged[field] = new_val
    return merged, None


def _apply_exact_percent_maps(
    target_map: dict[str, dict[str, Any]],
    value_json: dict[str, Any],
    *,
    prefix: str,
    rule_precedence: int,
    conflicts: list[str],
) -> None:
    exact_map = value_json.get(f"mandatory_{prefix}_exact_percent") or {}
    if not isinstance(exact_map, dict):
        return
    for key, percent in exact_map.items():
        key_str = str(key)
        entry = target_map.get(key_str, {"key": key_str})
        merged, conflict = _merge_mandatory_entry(
            entry,
            {"key": key_str, "exact_percent": float(percent)},
            incoming_precedence=rule_precedence,
            existing_precedence=rule_precedence,
        )
        if conflict:
            conflicts.append(conflict)
        else:
            target_map[key_str] = merged


def merge_scoped_mandatory_policy_payload(
    session: Session,
    base_payload: dict[str, Any],
    execution_context: PaperExecutionContext | None,
) -> dict[str, Any]:
    merged = dict(base_payload)
    context_errors = mandatory_policy_context_errors(session, execution_context)
    if context_errors:
        merged["mandatory_resolution_errors"] = context_errors
        return merged
    if execution_context is None or not execution_context.institution_id:
        merged["mandatory_resolution_errors"] = ["execution_context.institution_id"]
        return merged
    institution = session.get(Institution, execution_context.institution_id)
    if institution is None:
        merged["mandatory_resolution_errors"] = ["execution_context.institution_id"]
        return merged
    board_code = resolve_institution_board_code(session, execution_context.institution_id)
    rules, auth_errors = _resolve_authorized_mandatory_rules(
        session,
        board_code=board_code,
        institution=institution,
        teacher_id=execution_context.teacher_id,
        execution_context=execution_context,
    )
    if auth_errors:
        merged["mandatory_resolution_errors"] = auth_errors
        return merged
    if not rules:
        return merged
    conflicts: list[str] = []
    cognitive_by_key: dict[str, dict[str, Any]] = {
        str(item.get("key")): dict(item)
        for item in (merged.get("mandatory_cognitive_ranges") or [])
        if item.get("key")
    }
    competency_by_key: dict[str, dict[str, Any]] = {
        str(item.get("key")): dict(item)
        for item in (merged.get("mandatory_competency_ranges") or [])
        if item.get("key")
    }
    for rule in rules:
        value = dict(rule.value_json or {})
        enforcement = str((rule.metadata_json or {}).get("enforcement") or "mandatory")
        if enforcement == "weaken":
            continue
        rule_precedence = _SCOPE_PRECEDENCE.get(str(rule.scope_type), 0)
        _apply_exact_percent_maps(
            cognitive_by_key,
            value,
            prefix="cognitive",
            rule_precedence=rule_precedence,
            conflicts=conflicts,
        )
        _apply_exact_percent_maps(
            competency_by_key,
            value,
            prefix="competency",
            rule_precedence=rule_precedence,
            conflicts=conflicts,
        )
        for entry in value.get("mandatory_cognitive_ranges") or []:
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("key") or "")
            if not key:
                continue
            existing = cognitive_by_key.get(key)
            existing_precedence = rule_precedence if existing is None else rule_precedence
            merged_entry, conflict = _merge_mandatory_entry(
                existing,
                entry,
                incoming_precedence=rule_precedence,
                existing_precedence=existing_precedence,
            )
            if conflict:
                conflicts.append(conflict)
            else:
                cognitive_by_key[key] = merged_entry
        for entry in value.get("mandatory_competency_ranges") or []:
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("key") or "")
            if not key:
                continue
            existing = competency_by_key.get(key)
            merged_entry, conflict = _merge_mandatory_entry(
                existing,
                entry,
                incoming_precedence=rule_precedence,
                existing_precedence=rule_precedence,
            )
            if conflict:
                conflicts.append(conflict)
            else:
                competency_by_key[key] = merged_entry
    if conflicts:
        merged["mandatory_resolution_errors"] = conflicts
    merged["mandatory_cognitive_ranges"] = list(cognitive_by_key.values())
    merged["mandatory_competency_ranges"] = list(competency_by_key.values())
    merged["resolved_board_code"] = board_code
    return merged
