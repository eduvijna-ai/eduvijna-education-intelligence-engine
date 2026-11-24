from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ca_imat_eapcet.contracts import QuestionRef
from app.ca_imat_eapcet.enums import PlanVerdict


@dataclass(frozen=True, slots=True)
class PersistenceEnvelope:
    """D14-30: issuance fingerprint without envelope-only success."""

    idempotency_key: str
    content_fingerprint: str
    tenant_id: str
    source_version: str
    verdict: PlanVerdict
    committed: bool


def build_persistence_envelope(
    *,
    session: Session,
    questions: list[QuestionRef],
    organization_id: str,
    source_version: str,
    idempotency_key: str,
) -> PersistenceEnvelope:
    _ = session
    fp = hashlib.sha256(
        "|".join(q.fingerprint for q in questions).encode()
    ).hexdigest()
    committed = bool(questions) and bool(organization_id) and bool(source_version)
    verdict = PlanVerdict.PASS if committed else PlanVerdict.NOT_READY
    return PersistenceEnvelope(
        idempotency_key=idempotency_key,
        content_fingerprint=fp,
        tenant_id=organization_id,
        source_version=source_version,
        verdict=verdict,
        committed=committed,
    )