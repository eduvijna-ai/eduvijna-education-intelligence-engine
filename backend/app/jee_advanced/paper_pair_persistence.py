"""D12-CORE-05: Durable two-paper TestDefinition pair with idempotent SQLite replay."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TestDefinition, TestQuestion
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


@dataclass(frozen=True, slots=True)
class PaperPairPersistResult:
    outcome: PaperPairOutcome
    pair_correlation_id: str
    test_definition_ids: tuple[str, ...]
    checksum: str
    question_ids_by_paper: dict[str, list[str]]
    issue_codes: tuple[str, ...] = ()


PAIR_META_KIND = "jee_advanced_two_paper_v1"


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
    }
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _code_for_paper(idempotency_key: str, paper_code: str) -> str:
    digest = hashlib.sha256(f"{idempotency_key}:{paper_code}".encode()).hexdigest()[:16]
    return f"jee_adv_pair_{digest}"


def persist_two_paper_pair(
    session: Session,
    request: PaperPairPersistRequest,
) -> PaperPairPersistResult:
    fingerprint = _fingerprint(request)
    existing_codes = [
        _code_for_paper(request.idempotency_key, str(p.get("paper_code", f"paper_{i}")))
        for i, p in enumerate(request.paper_definitions)
    ]

    loaded: list[TestDefinition] = []
    for code in existing_codes:
        row = session.scalar(select(TestDefinition).where(TestDefinition.code == code))
        if row is not None:
            loaded.append(row)

    if loaded:
        stored_fp = str((loaded[0].metadata_json or {}).get("pair_fingerprint") or "")
        stored_org = str((loaded[0].metadata_json or {}).get("organization_id") or "")
        if stored_org != request.organization_id:
            return PaperPairPersistResult(
                outcome=PaperPairOutcome.CONFLICT,
                pair_correlation_id=request.pair_correlation_id,
                test_definition_ids=tuple(str(t.id) for t in loaded),
                checksum=stored_fp,
                question_ids_by_paper={},
                issue_codes=("tenant_mismatch",),
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
        for test in loaded:
            paper_code = str((test.metadata_json or {}).get("paper_code") or "")
            by_paper[paper_code] = [str(tq.question_id) for tq in test.questions]
        return PaperPairPersistResult(
            outcome=PaperPairOutcome.REPLAYED,
            pair_correlation_id=str((loaded[0].metadata_json or {}).get("pair_correlation_id")),
            test_definition_ids=tuple(str(t.id) for t in loaded),
            checksum=stored_fp,
            question_ids_by_paper=by_paper,
        )

    test_ids: list[str] = []
    created_by_paper: dict[str, list[str]] = {}
    for i, paper in enumerate(request.paper_definitions):
        paper_code = str(paper.get("paper_code") or f"paper_{i + 1}")
        code = _code_for_paper(request.idempotency_key, paper_code)
        test = TestDefinition(
            code=code,
            title=str(paper.get("title") or f"JEE Advanced {paper_code}"),
            exam_version_id=request.exam_version_id,
            blueprint_json=dict(paper.get("blueprint_json") or {}),
            status=TestStatus.DRAFT.value,
            metadata_json={
                "kind": PAIR_META_KIND,
                "pair_correlation_id": request.pair_correlation_id,
                "pair_fingerprint": fingerprint,
                "organization_id": request.organization_id,
                "institution_id": request.institution_id,
                "paper_code": paper_code,
                "idempotency_key": request.idempotency_key,
                "source_revision_snapshot": request.source_revision_snapshot,
                "blueprint_snapshot": request.blueprint_snapshot,
                "demonstration_only": paper.get("demonstration_only", True),
            },
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
    return PaperPairPersistResult(
        outcome=PaperPairOutcome.CREATED,
        pair_correlation_id=request.pair_correlation_id,
        test_definition_ids=tuple(test_ids),
        checksum=fingerprint,
        question_ids_by_paper=created_by_paper,
    )
