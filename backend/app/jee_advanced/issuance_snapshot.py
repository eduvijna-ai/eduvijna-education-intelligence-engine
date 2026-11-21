"""Immutable issuance snapshots and replay current-validity gate."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.jee_advanced.chain_question_binding import stored_mcq_answer_key
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

_CHAIN_REQUIRED_FIELDS = (
    "audit_ids",
    "proposed_answer_key",
    "author_claimed_answer_key",
    "author_item_id",
    "author_draft_fingerprint",
    "solver_display_fingerprint",
    "persisted_visible_fingerprint",
    "content_fingerprint",
    "stored_answer_key",
)


def question_issuance_snapshot(
    question: Question,
    *,
    organization_id: str,
    institution_id: str | None,
) -> dict[str, Any]:
    meta = dict(question.metadata_json or {})
    stored_key = stored_mcq_answer_key(question) or ""
    return {
        "question_id": str(question.id),
        "content_fingerprint": question_content_fingerprint(question),
        "status": str(question.status),
        "day6_validation_audit_id": str(meta.get("day6_validation_audit_id") or ""),
        "day6_solver_evidence_id": str(meta.get("day6_solver_evidence_id") or ""),
        "stored_answer_key": stored_key,
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
        snap = question_issuance_snapshot(
            q,
            organization_id=request.organization_id,
            institution_id=request.institution_id,
        )
        snapshots[chain.item_id] = snap
        author_gw = chain.audit_ids[0] if chain.audit_ids else ""
        solver_gw = chain.audit_ids[1] if len(chain.audit_ids) > 1 else ""
        reviewer_gw = chain.audit_ids[2] if len(chain.audit_ids) > 2 else ""
        chain_evidence[chain.item_id] = {
            "audit_ids": list(chain.audit_ids),
            "gateway_author_id": author_gw,
            "gateway_solver_id": solver_gw,
            "gateway_reviewer_id": reviewer_gw,
            "proposed_answer_key": chain.proposed_answer_key,
            "author_claimed_answer_key": chain.author_claimed_answer_key,
            "author_item_id": chain.author_item_id,
            "author_draft_fingerprint": chain.author_draft_fingerprint,
            "solver_display_fingerprint": chain.solver_display_fingerprint,
            "persisted_visible_fingerprint": chain.persisted_visible_fingerprint,
            "content_fingerprint": snap["content_fingerprint"],
            "stored_answer_key": snap["stored_answer_key"],
        }
    ordered_ids: list[str] = []
    for paper in request.paper_definitions:
        for item in paper.get("question_items") or []:
            ordered_ids.append(str(item.get("question_id") or ""))
    return {
        "issuance_record_version": "d12-f51-v1",
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


def verify_sibling_test_metadata(tests: list[TestDefinition]) -> tuple[bool, tuple[str, ...]]:
    if len(tests) != 2:
        return False, ("incomplete_pair_rows",)
    issues: list[str] = []
    meta0 = dict(tests[0].metadata_json or {})
    meta1 = dict(tests[1].metadata_json or {})
    for key in (
        "pair_fingerprint",
        "organization_id",
        "institution_id",
        "pair_correlation_id",
        "idempotency_key",
    ):
        if meta0.get(key) != meta1.get(key):
            issues.append(f"sibling_metadata_mismatch:{key}")
    if meta0.get("issuance_record") != meta1.get("issuance_record"):
        issues.append("sibling_issuance_record_mismatch")
    return (not issues, tuple(issues))


def verify_current_questions_for_replay(
    session: Session,
    request: Any,
    *,
    stored_record: dict[str, Any],
) -> tuple[bool, tuple[str, ...]]:
    """Re-verify live Question rows and chain evidence before returning REPLAYED."""

    issues: list[str] = []
    if str(stored_record.get("issuance_record_version") or "") not in {
        "d12-f51-v1",
        "d12-f50-v1",
        "d12-f49-v1",
    }:
        issues.append("issuance_record_version_unsupported")

    ordered_ids = _question_ids_from_request(request)
    stored_ordered = list(stored_record.get("ordered_question_ids") or [])
    if stored_ordered != ordered_ids:
        issues.append("ordered_question_ids_mismatch")

    snapshots = dict(stored_record.get("question_snapshots") or {})
    if not snapshots or len(snapshots) != len(ordered_ids):
        issues.append("issuance_snapshot_incomplete")
        return False, tuple(dict.fromkeys(issues))

    stored_chain = dict(stored_record.get("chain_evidence") or {})
    if not stored_chain or len(stored_chain) != len(ordered_ids):
        issues.append("chain_evidence_incomplete")

    for qid in ordered_ids:
        snap = snapshots.get(qid)
        if snap is None:
            issues.append(f"issuance_snapshot_question_missing:{qid}")
            continue
        ev = stored_chain.get(qid)
        if ev is None:
            issues.append(f"chain_evidence_missing:{qid}")
            continue

        for field in _CHAIN_REQUIRED_FIELDS:
            val = ev.get(field)
            if val is None or (isinstance(val, str) and not val.strip()):
                issues.append(f"chain_evidence_field_missing:{qid}:{field}")
            if field == "audit_ids" and isinstance(val, list) and len(val) < 3:
                issues.append(f"chain_gateway_ids_incomplete:{qid}")

        author_fp = str(ev.get("author_draft_fingerprint") or "")
        persisted_fp = str(ev.get("persisted_visible_fingerprint") or "")
        solver_fp = str(ev.get("solver_display_fingerprint") or "")
        if not author_fp or not persisted_fp or not solver_fp:
            issues.append(f"chain_fingerprint_incomplete:{qid}")
        elif author_fp != persisted_fp:
            issues.append(f"stored_author_fingerprint_mismatch:{qid}")
        elif author_fp != solver_fp:
            issues.append(f"stored_solver_display_fingerprint_mismatch:{qid}")

        stored_key = str(snap.get("stored_answer_key") or "")
        author_key = str(ev.get("author_claimed_answer_key") or "")
        solver_key = str(ev.get("proposed_answer_key") or "")
        if stored_key and author_key and stored_key != author_key:
            issues.append(f"stored_author_answer_mismatch:{qid}")
        if stored_key and solver_key and stored_key != solver_key:
            issues.append(f"stored_solver_answer_mismatch:{qid}")
        if author_key and solver_key and author_key != solver_key:
            issues.append(f"stored_author_solver_mismatch:{qid}")

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
        live_key = stored_mcq_answer_key(question) or ""
        if live_key != stored_key:
            issues.append(f"question_stored_answer_drift:{qid}")
        if question_day9_veto(question):
            issues.append(f"day9_veto:{qid}")
        meta = dict(question.metadata_json or {})
        live_audit = str(meta.get("day6_validation_audit_id") or "")
        live_solver = str(meta.get("day6_solver_evidence_id") or "")
        snap_audit = str(snap.get("day6_validation_audit_id") or "")
        snap_solver = str(snap.get("day6_solver_evidence_id") or "")
        if live_audit != snap_audit:
            issues.append(f"day6_audit_id_drift:{qid}")
        if live_solver != snap_solver:
            issues.append(f"day6_solver_id_drift:{qid}")
        ok, reason = validation_run_covers_question(
            session,
            run_id=snap_audit,
            question=question,
            organization_id=request.organization_id,
            institution_id=request.institution_id,
        )
        if not ok:
            issues.append(reason or f"validation_stale:{qid}")

    if dict(stored_record.get("source_revision_snapshot") or {}) != dict(
        request.source_revision_snapshot
    ):
        issues.append("source_snapshot_drift")
    if dict(stored_record.get("blueprint_snapshot") or {}) != dict(
        request.blueprint_snapshot
    ):
        issues.append("blueprint_snapshot_drift")

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