from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ca_imat_eapcet.containment import CONTAINMENT_NOTE, ISSUANCE_DISABLED
from app.ca_imat_eapcet.contracts import QuestionRef
from app.ca_imat_eapcet.enums import IssueCode, PlanVerdict


@dataclass(frozen=True, slots=True)
class PersistenceEnvelope:
    """D14-30: canonical issuance outcome; disabled under safety containment."""

    idempotency_key: str
    content_fingerprint: str
    tenant_id: str
    source_version: str
    verdict: PlanVerdict
    committed: bool
    persisted_question_ids: tuple[str, ...]
    issue_codes: tuple[IssueCode, ...]


def _content_fingerprint(questions: list[QuestionRef]) -> str:
    parts = [f"{q.fingerprint}:{q.marks_if_correct}:{q.marks_if_incorrect}" for q in questions]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def attempt_canonical_issuance(
    *,
    session: Session,
    questions: list[QuestionRef],
    organization_id: str,
    institution_id: str,
    exam_version_id: str,
    source_version: str,
    idempotency_key: str,
    exam_pack_code: str = "ca_foundation",
) -> PersistenceEnvelope:
    """D14-30 containment: no session access, writes, reads, or replay success."""

    _ = (
        session,
        organization_id,
        institution_id,
        exam_version_id,
        source_version,
        exam_pack_code,
        questions,
        ISSUANCE_DISABLED,
    )
    fp = _content_fingerprint(questions) if questions else ""
    issues: tuple[IssueCode, ...] = (IssueCode.ISSUANCE_CONTAINED, IssueCode.ENVELOPE_ONLY_SUCCESS)
    if not idempotency_key or not idempotency_key.strip():
        issues = (
            IssueCode.VALIDATION_NOT_PROVEN,
            IssueCode.ISSUANCE_CONTAINED,
            IssueCode.ENVELOPE_ONLY_SUCCESS,
        )
    return PersistenceEnvelope(
        idempotency_key=idempotency_key or "",
        content_fingerprint=fp,
        tenant_id=organization_id,
        source_version=source_version,
        verdict=PlanVerdict.NOT_READY,
        committed=False,
        persisted_question_ids=(),
        issue_codes=issues,
    )


ISSUANCE_STATUS_DOC = CONTAINMENT_NOTE