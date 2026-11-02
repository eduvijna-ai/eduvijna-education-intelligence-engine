from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import PolicyScopeType, SourceRevisionStatus
from app.models.policy import PolicyRule
from app.models.source import SourceRevision, policy_rule_source_revisions
from app.models.tenancy import Institution
from app.paper_distribution.execution_context import PaperExecutionContext

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


def _revision_authorized_for_policy(session: Session, rule: PolicyRule) -> bool:
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
        if revision is None:
            return False
        if revision.status != SourceRevisionStatus.ACTIVE.value:
            return False
        if not revision.approval_fingerprint or not revision.approved_by:
            return False
    return True


def _active_rules_for_context(
    session: Session,
    *,
    board_code: str | None,
    institution: Institution | None,
    teacher_id: str | None,
    on_date: date | None = None,
) -> list[PolicyRule]:
    effective = on_date or date.today()
    rules = session.scalars(
        select(PolicyRule).where(
            PolicyRule.policy_key == PAPER_MANDATORY_POLICY_KEY,
            PolicyRule.active.is_(True),
        )
    ).all()
    selected: list[PolicyRule] = []
    for rule in rules:
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
        if not _revision_authorized_for_policy(session, rule):
            continue
        selected.append(rule)
    return sorted(
        selected,
        key=lambda item: (-_SCOPE_PRECEDENCE.get(str(item.scope_type), 0), -item.priority),
    )


def _tighten_range_entry(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for field in ("min_percent", "max_percent", "exact_count", "exact_percent"):
        new_val = incoming.get(field)
        if new_val is None:
            continue
        old_val = merged.get(field)
        if field in {"min_percent", "exact_count"} and old_val is not None:
            merged[field] = max(float(old_val), float(new_val))
        elif field in {"max_percent", "exact_percent"} and old_val is not None:
            merged[field] = min(float(old_val), float(new_val))
        else:
            merged[field] = new_val
    return merged


def merge_scoped_mandatory_policy_payload(
    session: Session,
    base_payload: dict[str, Any],
    execution_context: PaperExecutionContext | None,
) -> dict[str, Any]:
    if execution_context is None or not execution_context.institution_id:
        return base_payload
    institution = session.get(Institution, execution_context.institution_id)
    board_code = resolve_institution_board_code(session, execution_context.institution_id)
    if execution_context.board_code and board_code and execution_context.board_code != board_code:
        return base_payload
    rules = _active_rules_for_context(
        session,
        board_code=board_code,
        institution=institution,
        teacher_id=execution_context.teacher_id,
    )
    if not rules:
        return base_payload
    merged = dict(base_payload)
    cognitive_ranges = list(merged.get("mandatory_cognitive_ranges") or [])
    competency_ranges = list(merged.get("mandatory_competency_ranges") or [])
    cognitive_by_key = {
        str(item.get("key")): dict(item)
        for item in cognitive_ranges
        if item.get("key")
    }
    competency_by_key = {
        str(item.get("key")): dict(item) for item in competency_ranges if item.get("key")
    }
    for rule in rules:
        value = dict(rule.value_json or {})
        enforcement = str((rule.metadata_json or {}).get("enforcement") or "mandatory")
        if enforcement == "weaken":
            continue
        for entry in value.get("mandatory_cognitive_ranges") or []:
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("key") or "")
            if not key:
                continue
            cognitive_by_key[key] = _tighten_range_entry(
                cognitive_by_key.get(key, {"key": key}), entry
            )
        for entry in value.get("mandatory_competency_ranges") or []:
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("key") or "")
            if not key:
                continue
            competency_by_key[key] = _tighten_range_entry(
                competency_by_key.get(key, {"key": key}), entry
            )
    merged["mandatory_cognitive_ranges"] = list(cognitive_by_key.values())
    merged["mandatory_competency_ranges"] = list(competency_by_key.values())
    merged["resolved_board_code"] = board_code
    return merged
