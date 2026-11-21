"""Immutable issuance snapshots and replay current-validity gate (Issue #49)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.jee_advanced.independent_solver_proof import validation_run_covers_question
from app.jee_advanced.orchestration_chain import OrchestrationChainResult
from app.jee_advanced.persisted_question_loader import (
    PersistedAnswerScope,
    load_persisted_question,
)
from app.jee_advanced.question_fingerprint import question_content_fingerprint
from app.jee_advanced.stored_answer_resolution import question_day9_veto
from app.models import Question, TestDefinition
from app.models.enums import QuestionStatus


def question_issuance_snapshot(
    question: Question,
    *,
    organization_id: str,
    institution_id: str | None,
) -> dict[str, Any]:
    meta = dict(question.metadata_json or {})
    return {
        "question_id": str(question.id),
        "content_fingerprint": question_content_fingerprint(question),
        "status": str(question.status),
        "day6_validation_audit_id": str(meta.get("day6_validation_audit_id") or ""),
        "day6_solver_evidence_id": str(meta.get("day6_solver_evidence_id") or ""),
        "organization_id": organization_id,
        "institution_id": institution_id or "",
        "exam_version_id": str(question.exam_version_id or ""),
    }


def build_issuance_record(
    request: Any,
    *,
    questions: tuple[Question, Question],
    chains: tuple[OrchestrationChainResult, ...],
) -> dict[str, Any]:
    by_id = {str(q.id): q for q in questions}
    snapshots: dict[str, dict[str, Any]] = {}
    chain_evidence: dict[str, dict[str, Any]] = {}
    for chain in chains:
        q = by_id.get(chain.item_id)
        if q is None:
            continue
        snapshots[chain.item_id] = question_issuance_snapshot(
            q,
            organization_id=request.organization_id,
            institution_id=request.institution_id,
        )
        chain_evidence[chain.item_id] = {
            "audit_ids": list(chain.audit_ids),
            "proposed_answer_key": chain.proposed_answer_key,
            "author_item_id": chain.author_item_id,
            "content_fingerprint": snapshots[chain.item_id]["content_fingerprint"],
        }
    ordered_ids: list[str] = []
    for paper in request.paper_definitions:
        for item in paper.get("question_items") or []:
            ordered_ids.append(str(item.get("question_id") or ""))
    return {
        "issuance_record_version": "d12-f49-v1",
        "pair_fingerprint": None,
        "ordered_question_ids": ordered_ids,
        "question_snapshots": snapshots,
        "chain_evidence": chain_evidence,
        "source_revision_snapshot": dict(request.source_revision_snapshot),
        "blueprint_snapshot": dict(request.blueprint_snapshot),
    }


def _question_ids_from_request(request: Any) -> list[str]:
    ids: list[str] = []
    for paper in request.paper_definitions:
        for item in paper.get("question_items") or []:
            qid = str(item.get("question_id") or "")
            if qid:
                ids.append(qid)
    return ids


def verify_current_questions_for_replay(
    session: Session,
    request: Any,
    *,
    stored_record: dict[str, Any],
) -> tuple[bool, tuple[str, ...]]:
    """Re-verify live Question rows before returning REPLAYED."""

    issues: list[str] = []
    snapshots = dict(stored_record.get("question_snapshots") or {})
    if not snapshots:
        issues.append("issuance_snapshot_missing")
        return False, tuple(issues)

    for qid in _question_ids_from_request(request):
        snap = snapshots.get(qid)
        if snap is None:
            issues.append(f"issuance_snapshot_question_missing:{qid}")
            continue
        question, load_issues = load_persisted_question(
            session,
            qid,
            PersistedAnswerScope(
                organization_id=request.organization_id,
                institution_id=request.institution_id,
                exam_version_id=request.exam_version_id,
                expected_family="mcq",
            ),
        )
        if load_issues:
            issues.extend(load_issues)
            continue
        assert question is not None
        if question.status != QuestionStatus.APPROVED.value:
            issues.append(f"question_not_approved:{qid}")
        fp = question_content_fingerprint(question)
        if fp != str(snap.get("content_fingerprint") or ""):
            issues.append(f"question_content_drift:{qid}")
        if question_day9_veto(question):
            issues.append(f"day9_veto:{qid}")
        ok, reason = validation_run_covers_question(
            session,
            run_id=str(snap.get("day6_validation_audit_id") or ""),
            question=question,
            organization_id=request.organization_id,
            institution_id=request.institution_id,
        )
        if not ok:
            issues.append(reason or f"validation_stale:{qid}")

    if issues:
        return False, tuple(dict.fromkeys(issues))
    return True, ()


def load_stored_issuance_record(tests: list[TestDefinition]) -> dict[str, Any] | None:
    if not tests:
        return None
    record = (tests[0].metadata_json or {}).get("issuance_record")
    if not isinstance(record, dict):
        return None
    sibling = (tests[1].metadata_json or {}).get("issuance_record") if len(tests) > 1 else None
    if sibling != record:
        return None
    return record