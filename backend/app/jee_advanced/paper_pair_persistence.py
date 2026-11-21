"""D12-CORE-05: Durable two-paper TestDefinition pair with idempotent SQLite replay."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.jee_advanced.constants import PAPER_1_CODE, PAPER_2_CODE
from app.jee_advanced.enums import AdvancedProfileKind
from app.jee_advanced.issuance_snapshot import (
    load_stored_issuance_record,
    verify_current_questions_for_replay,
    verify_sibling_test_metadata,
)
from app.jee_advanced.source_storage import metadata_marks_synthetic
from app.models import ExamVersion, Question, TestDefinition, TestQuestion
from app.models.enums import TestStatus


class PaperPairOutcome(StrEnum):
    CREATED = "created"
    REPLAYED = "replayed"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class PaperPairPersistRequest:
    idempotency_key: str
    organization_id: str
    institution_id: str | None
    exam_version_id: str
    pair_correlation_id: str
    paper_definitions: tuple[dict[str, Any], dict[str, Any]]
    source_revision_snapshot: dict[str, str]
    blueprint_snapshot: dict[str, Any]
    synthetic_labeled_test_mode: bool = False


@dataclass(frozen=True, slots=True)
class PaperPairPersistResult:
    outcome: PaperPairOutcome
    pair_correlation_id: str
    test_definition_ids: tuple[str, ...]
    checksum: str
    question_ids_by_paper: dict[str, list[str]]
    issue_codes: tuple[str, ...] = ()


PAIR_META_KIND = "jee_advanced_two_paper_v1"
_REQUIRED_PAPERS = (PAPER_1_CODE, PAPER_2_CODE)


def _fingerprint(request: PaperPairPersistRequest) -> str:
    body = {
        "idempotency_key": request.idempotency_key,
        "organization_id": request.organization_id,
        "institution_id": request.institution_id,
        "exam_version_id": request.exam_version_id,
        "pair_correlation_id": request.pair_correlation_id,
        "papers": request.paper_definitions,
        "source_revision_snapshot": request.source_revision_snapshot,
        "blueprint_snapshot": request.blueprint_snapshot,
        "synthetic_labeled_test_mode": request.synthetic_labeled_test_mode,
    }
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _code_for_paper(idempotency_key: str, paper_code: str) -> str:
    digest = hashlib.sha256(f"{idempotency_key}:{paper_code}".encode()).hexdigest()[:16]
    return f"jee_adv_pair_{digest}"


def _paper_codes(request: PaperPairPersistRequest) -> list[str]:
    return [
        str(p.get("paper_code") or f"paper_{i + 1}")
        for i, p in enumerate(request.paper_definitions)
    ]


def _synthetic_test_persistence_allowed(session: Session, exam_version_id: str) -> bool:
    version = session.get(ExamVersion, exam_version_id)
    if version is None:
        return False
    profile = str((version.metadata_json or {}).get("profile_kind") or "")
    return profile == AdvancedProfileKind.SYNTHETIC_DEMO.value


def _item_marks_valid(item: dict[str, Any]) -> tuple[bool, str | None]:
    for key in ("marks", "negative_marks"):
        if key not in item or item[key] is None:
            continue
        val = item[key]
        if not isinstance(val, (int, float)) or not math.isfinite(float(val)):
            return False, f"nonfinite_{key}"
        if float(val) < 0:
            return False, f"negative_{key}"
    return True, None


def _paper_questions_match(
    test: TestDefinition, paper: dict[str, Any]
) -> tuple[bool, str | None]:
    items = list(paper.get("question_items") or [])
    ordered = sorted(test.questions, key=lambda row: row.sequence)
    if len(ordered) != len(items):
        return False, "question_row_count_mismatch"
    for row, item in zip(ordered, items, strict=True):
        if str(row.question_id) != str(item.get("question_id")):
            return False, "question_id_mismatch"
        if str(row.section_code or "") != str(item.get("section_code") or ""):
            return False, "section_code_mismatch"
        if item.get("marks") is not None:
            row_marks = row.marks
            if row_marks is None or not math.isclose(
                float(row_marks), float(item["marks"]), rel_tol=0, abs_tol=1e-9
            ):
                return False, "marks_mismatch"
        if item.get("negative_marks") is not None:
            stored = row.negative_marks
            if stored is None or not math.isclose(
                float(stored), float(item["negative_marks"]), rel_tol=0, abs_tol=1e-9
            ):
                return False, "negative_marks_mismatch"
    return True, None


def _validate_request_shape(session: Session, request: PaperPairPersistRequest) -> tuple[str, ...]:
    issues: list[str] = []
    if request.synthetic_labeled_test_mode and not _synthetic_test_persistence_allowed(
        session, request.exam_version_id
    ):
        issues.append("synthetic_test_mode_not_allowed")
    codes = _paper_codes(request)
    if len(codes) != 2 or len(set(codes)) != 2:
        issues.append("invalid_paper_count")
    if set(codes) != set(_REQUIRED_PAPERS):
        issues.append("missing_required_paper_pair")

    used_questions: set[str] = set()
    for paper in request.paper_definitions:
        for item in paper.get("question_items") or []:
            marks_ok, mark_issue = _item_marks_valid(item)
            if not marks_ok:
                issues.append(mark_issue or "invalid_item_marks")
            qid = str(item.get("question_id") or "")
            if not qid:
                issues.append("missing_question_id")
                continue
            if qid in used_questions:
                issues.append("duplicate_cross_paper_question")
            used_questions.add(qid)
            question = session.get(Question, qid)
            if question is None:
                issues.append("unknown_question_id")
                continue
            meta = dict(question.metadata_json or {})
            q_org = str(meta.get("organization_id") or "")
            if q_org and q_org != request.organization_id:
                issues.append("question_tenant_mismatch")
            if question.exam_version_id != request.exam_version_id:
                issues.append("question_exam_version_mismatch")
            if request.synthetic_labeled_test_mode:
                if not meta.get("d12_core_test_fixture"):
                    issues.append("unlabeled_test_question")
            elif metadata_marks_synthetic(meta):
                issues.append("synthetic_question_in_reference_mode")

    if not request.synthetic_labeled_test_mode:
        if not request.source_revision_snapshot:
            issues.append("missing_source_snapshot")
        if not request.blueprint_snapshot:
            issues.append("missing_blueprint_snapshot")

    return tuple(issues)


def _ordered_ids(test: TestDefinition) -> list[str]:
    ordered = sorted(test.questions, key=lambda row: row.sequence)
    return [str(row.question_id) for row in ordered]


def _match_existing_pair(
    session: Session, request: PaperPairPersistRequest
) -> PaperPairPersistResult | None:
    """Read-only pair resolution. None when no rows exist yet (issue #48 preflight)."""

    fingerprint = _fingerprint(request)
    existing_codes = [
        _code_for_paper(request.idempotency_key, code) for code in _paper_codes(request)
    ]

    with session.no_autoflush:
        loaded: list[TestDefinition] = []
        for code in existing_codes:
            row = session.scalar(select(TestDefinition).where(TestDefinition.code == code))
            if row is not None:
                loaded.append(row)

    if not loaded:
        return None

    if len(loaded) != 2:
        return PaperPairPersistResult(
            outcome=PaperPairOutcome.CONFLICT,
            pair_correlation_id=request.pair_correlation_id,
            test_definition_ids=tuple(str(t.id) for t in loaded),
            checksum="",
            question_ids_by_paper={},
            issue_codes=("incomplete_pair_rows",),
        )
    sib_ok, sib_issues = verify_sibling_test_metadata(loaded)
    if not sib_ok:
        return PaperPairPersistResult(
            outcome=PaperPairOutcome.CONFLICT,
            pair_correlation_id=request.pair_correlation_id,
            test_definition_ids=tuple(str(t.id) for t in loaded),
            checksum=str((loaded[0].metadata_json or {}).get("pair_fingerprint") or ""),
            question_ids_by_paper={},
            issue_codes=sib_issues,
        )
    stored_fp = str((loaded[0].metadata_json or {}).get("pair_fingerprint") or "")
    stored_org = str((loaded[0].metadata_json or {}).get("organization_id") or "")
    stored_corr = str((loaded[0].metadata_json or {}).get("pair_correlation_id") or "")
    stored_inst = str((loaded[0].metadata_json or {}).get("institution_id") or "")
    if stored_org != request.organization_id:
        return PaperPairPersistResult(
            outcome=PaperPairOutcome.CONFLICT,
            pair_correlation_id=request.pair_correlation_id,
            test_definition_ids=tuple(str(t.id) for t in loaded),
            checksum=stored_fp,
            question_ids_by_paper={},
            issue_codes=("tenant_mismatch",),
        )
    if (request.institution_id or "") != stored_inst:
        return PaperPairPersistResult(
            outcome=PaperPairOutcome.CONFLICT,
            pair_correlation_id=request.pair_correlation_id,
            test_definition_ids=tuple(str(t.id) for t in loaded),
            checksum=stored_fp,
            question_ids_by_paper={},
            issue_codes=("institution_mismatch",),
        )
    if stored_corr != request.pair_correlation_id:
        return PaperPairPersistResult(
            outcome=PaperPairOutcome.CONFLICT,
            pair_correlation_id=request.pair_correlation_id,
            test_definition_ids=tuple(str(t.id) for t in loaded),
            checksum=stored_fp,
            question_ids_by_paper={},
            issue_codes=("pair_correlation_mismatch",),
        )
    if stored_fp != fingerprint:
        return PaperPairPersistResult(
            outcome=PaperPairOutcome.CONFLICT,
            pair_correlation_id=request.pair_correlation_id,
            test_definition_ids=tuple(str(t.id) for t in loaded),
            checksum=stored_fp,
            question_ids_by_paper={},
            issue_codes=("idempotency_payload_mismatch",),
        )
    by_paper: dict[str, list[str]] = {}
    paper_by_code = {str(p.get("paper_code")): p for p in request.paper_definitions}
    for test in loaded:
        paper_code = str((test.metadata_json or {}).get("paper_code") or "")
        paper_def = paper_by_code.get(paper_code)
        if paper_def is None:
            return PaperPairPersistResult(
                outcome=PaperPairOutcome.CONFLICT,
                pair_correlation_id=request.pair_correlation_id,
                test_definition_ids=tuple(str(t.id) for t in loaded),
                checksum=stored_fp,
                question_ids_by_paper={},
                issue_codes=("unknown_paper_code",),
            )
        ok, mismatch = _paper_questions_match(test, paper_def)
        by_paper[paper_code] = _ordered_ids(test)
        if not ok:
            return PaperPairPersistResult(
                outcome=PaperPairOutcome.CONFLICT,
                pair_correlation_id=request.pair_correlation_id,
                test_definition_ids=tuple(str(t.id) for t in loaded),
                checksum=stored_fp,
                question_ids_by_paper=by_paper,
                issue_codes=(mismatch or "question_payload_mismatch",),
            )
        stored_snap = (test.metadata_json or {}).get("source_revision_snapshot")
        if stored_snap != request.source_revision_snapshot:
            return PaperPairPersistResult(
                outcome=PaperPairOutcome.CONFLICT,
                pair_correlation_id=request.pair_correlation_id,
                test_definition_ids=tuple(str(t.id) for t in loaded),
                checksum=stored_fp,
                question_ids_by_paper=by_paper,
                issue_codes=("source_snapshot_drift",),
            )
        stored_blue = (test.metadata_json or {}).get("blueprint_snapshot")
        if stored_blue != request.blueprint_snapshot:
            return PaperPairPersistResult(
                outcome=PaperPairOutcome.CONFLICT,
                pair_correlation_id=request.pair_correlation_id,
                test_definition_ids=tuple(str(t.id) for t in loaded),
                checksum=stored_fp,
                question_ids_by_paper=by_paper,
                issue_codes=("blueprint_snapshot_drift",),
            )
    record = load_stored_issuance_record(loaded)
    if record is None:
        return PaperPairPersistResult(
            outcome=PaperPairOutcome.CONFLICT,
            pair_correlation_id=request.pair_correlation_id,
            test_definition_ids=tuple(str(t.id) for t in loaded),
            checksum=stored_fp,
            question_ids_by_paper=by_paper,
            issue_codes=("issuance_snapshot_missing",),
        )
    with session.no_autoflush:
        snap_ok, snap_issues = verify_current_questions_for_replay(
            session, request, stored_record=record
        )
    if not snap_ok:
        return PaperPairPersistResult(
            outcome=PaperPairOutcome.CONFLICT,
            pair_correlation_id=request.pair_correlation_id,
            test_definition_ids=tuple(str(t.id) for t in loaded),
            checksum=stored_fp,
            question_ids_by_paper=by_paper,
            issue_codes=snap_issues,
        )
    return PaperPairPersistResult(
        outcome=PaperPairOutcome.REPLAYED,
        pair_correlation_id=stored_corr,
        test_definition_ids=tuple(str(t.id) for t in loaded),
        checksum=stored_fp,
        question_ids_by_paper=by_paper,
    )


def preflight_two_paper_pair(
    session: Session, request: PaperPairPersistRequest
) -> PaperPairPersistResult | None:
    """Shape-check and idempotent resolution before gateway; None when issuance may proceed."""

    with session.no_autoflush:
        shape_issues = _validate_request_shape(session, request)
        if shape_issues:
            return PaperPairPersistResult(
                outcome=PaperPairOutcome.CONFLICT,
                pair_correlation_id=request.pair_correlation_id,
                test_definition_ids=(),
                checksum="",
                question_ids_by_paper={},
                issue_codes=shape_issues,
            )
        return _match_existing_pair(session, request)


def persist_two_paper_pair(
    session: Session,
    request: PaperPairPersistRequest,
    *,
    issuance_record: dict[str, Any] | None = None,
) -> PaperPairPersistResult:
    shape_issues = _validate_request_shape(session, request)
    if shape_issues:
        return PaperPairPersistResult(
            outcome=PaperPairOutcome.CONFLICT,
            pair_correlation_id=request.pair_correlation_id,
            test_definition_ids=(),
            checksum="",
            question_ids_by_paper={},
            issue_codes=shape_issues,
        )

    fingerprint = _fingerprint(request)
    matched = _match_existing_pair(session, request)
    if matched is not None:
        return matched

    test_ids: list[str] = []
    created_by_paper: dict[str, list[str]] = {}
    try:
        for i, paper in enumerate(request.paper_definitions):
            paper_code = str(paper.get("paper_code") or f"paper_{i + 1}")
            code = _code_for_paper(request.idempotency_key, paper_code)
            meta: dict[str, Any] = {
                "kind": PAIR_META_KIND,
                "pair_correlation_id": request.pair_correlation_id,
                "pair_fingerprint": fingerprint,
                "organization_id": request.organization_id,
                "institution_id": request.institution_id,
                "paper_code": paper_code,
                "idempotency_key": request.idempotency_key,
                "source_revision_snapshot": request.source_revision_snapshot,
                "blueprint_snapshot": request.blueprint_snapshot,
                "demonstration_only": request.synthetic_labeled_test_mode,
                "synthetic_labeled_test_mode": request.synthetic_labeled_test_mode,
            }
            if issuance_record is not None:
                stored = dict(issuance_record)
                stored["pair_fingerprint"] = fingerprint
                meta["issuance_record"] = stored
            test = TestDefinition(
                code=code,
                title=str(paper.get("title") or f"JEE Advanced {paper_code}"),
                exam_version_id=request.exam_version_id,
                blueprint_json=dict(paper.get("blueprint_json") or {}),
                status=TestStatus.DRAFT.value,
                metadata_json=meta,
            )
            session.add(test)
            session.flush()
            test_ids.append(str(test.id))
            q_ids: list[str] = []
            for seq, item in enumerate(paper.get("question_items") or [], start=1):
                qid = str(item["question_id"])
                q_ids.append(qid)
                session.add(
                    TestQuestion(
                        test_definition_id=test.id,
                        question_id=qid,
                        sequence=seq,
                        section_code=str(item.get("section_code") or ""),
                        marks=float(item.get("marks") or 0),
                        negative_marks=float(item["negative_marks"])
                        if item.get("negative_marks") is not None
                        else None,
                        metadata_json=dict(item.get("metadata_json") or {}),
                    )
                )
            created_by_paper[paper_code] = q_ids

        session.flush()
    except IntegrityError:
        session.rollback()
        return PaperPairPersistResult(
            outcome=PaperPairOutcome.CONFLICT,
            pair_correlation_id=request.pair_correlation_id,
            test_definition_ids=(),
            checksum="",
            question_ids_by_paper={},
            issue_codes=("persistence_integrity_conflict",),
        )
    return PaperPairPersistResult(
        outcome=PaperPairOutcome.CREATED,
        pair_correlation_id=request.pair_correlation_id,
        test_definition_ids=tuple(test_ids),
        checksum=fingerprint,
        question_ids_by_paper=created_by_paper,
    )