"""Trusted synthetic harness — server-side attestation only (D15-F01)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from app.learner_intelligence.contracts import (
    CreateAttemptRequest,
    SnapshotItem,
    TrustedActorContext,
)
from app.learner_intelligence.enums import EligibilityTrustMode, PerformanceMode
from app.learner_intelligence.snapshot import (
    canonicalize_items,
    compute_assessment_fingerprint,
    compute_item_fingerprint,
)

HARNESS_ATTESTATION_SALT = "eduvijna-d15-internal-harness-v2"
TRUSTED_CATALOG_KEY_TWO_ITEM = "d15-synthetic-two-item-v1"
TRUSTED_DIAGNOSTIC_EVIDENCE_REF = "d15-harness-day9-synthetic-v1"

_BLOCKED_EXAM_PACK_PREFIXES = (
    "day11_",
    "ca_",
    "imat_",
    "eapcet_",
    "jee_",
    "cuet_",
    "clat_",
)


def build_two_item_catalog_items() -> list[SnapshotItem]:
    from decimal import Decimal

    from app.diagnostic_intelligence.enums import DiagnosticValidationStatus
    from app.learner_intelligence.contracts import SnapshotOption

    item1 = SnapshotItem(
        item_sequence=1,
        question_id="q-d15-001",
        stem_text="What is 2 + 2?",
        question_type="single_choice",
        options=[
            SnapshotOption(option_key="A", display_text="3", is_correct=False),
            SnapshotOption(option_key="B", display_text="4", is_correct=True),
            SnapshotOption(option_key="C", display_text="5", is_correct=False),
        ],
        marks_if_correct=Decimal("4"),
        marks_if_incorrect=Decimal("-1"),
        marks_if_blank=Decimal("0"),
        concept_codes=["arithmetic.addition"],
        learning_outcome_ids=["lo-add-v1"],
        competency_codes=["comp-quant"],
        difficulty_band="easy",
        cognitive_level="remember",
        source_version="synthetic@v1",
        content_fingerprint="",
        diagnostic_tags_json=[
            {
                "item_id": "q-d15-001",
                "option_key": "A",
                "is_correct": False,
                "misconception_code": "OFF_BY_ONE_LOW",
                "taxonomy_version": "misconception-taxonomy@v1",
                "validation_status": DiagnosticValidationStatus.PASS.value,
                "evidence_refs": [TRUSTED_DIAGNOSTIC_EVIDENCE_REF],
            }
        ],
    )
    item2 = SnapshotItem(
        item_sequence=2,
        question_id="q-d15-002",
        stem_text="Solve: 3 + 4",
        question_type="numeric",
        options=[],
        marks_if_correct=Decimal("4"),
        marks_if_incorrect=Decimal("0"),
        numeric_answer="7",
        numeric_tolerance=Decimal("0"),
        concept_codes=["arithmetic.addition"],
        source_version="synthetic@v1",
        content_fingerprint="",
        diagnostic_tags_json=[],
    )
    return _with_server_fingerprints([item1, item2])


_CATALOG: dict[str, Callable[[], list[SnapshotItem]]] = {
    TRUSTED_CATALOG_KEY_TWO_ITEM: build_two_item_catalog_items,
}


def _with_server_fingerprints(items: list[SnapshotItem]) -> list[SnapshotItem]:
    return [
        item.model_copy(update={"content_fingerprint": compute_item_fingerprint(item)})
        for item in items
    ]


def trusted_catalog_items(catalog_key: str) -> list[SnapshotItem]:
    builder = _CATALOG.get(catalog_key)
    if builder is None:
        raise KeyError(catalog_key)
    return builder()


def compute_harness_attestation(catalog_key: str, items: list[SnapshotItem]) -> str:
    binding = compute_assessment_fingerprint(items)
    raw = f"{HARNESS_ATTESTATION_SALT}|{catalog_key}|{binding}"
    return hashlib.sha256(raw.encode()).hexdigest()


def verify_harness_attestation(
    catalog_key: str,
    items: list[SnapshotItem],
    attestation: str,
) -> bool:
    if catalog_key not in _CATALOG:
        return False
    canonical = canonicalize_items(trusted_catalog_items(catalog_key))
    supplied = canonicalize_items(items)
    if canonical != supplied:
        return False
    expected = compute_harness_attestation(catalog_key, items)
    return attestation == expected and len(attestation) == 64


def is_blocked_exam_pack(exam_pack_code: str | None) -> bool:
    if not exam_pack_code:
        return False
    lowered = exam_pack_code.lower()
    return any(lowered.startswith(p) for p in _BLOCKED_EXAM_PACK_PREFIXES)


def build_harness_create_request(
    actor: TrustedActorContext,
    *,
    catalog_key: str = TRUSTED_CATALOG_KEY_TWO_ITEM,
    assessment_key: str,
    idempotency_key: str,
    performance_mode: PerformanceMode = PerformanceMode.PRACTICE,
) -> CreateAttemptRequest:
    items = trusted_catalog_items(catalog_key)
    attestation = compute_harness_attestation(catalog_key, items)
    return CreateAttemptRequest(
        actor=actor,
        trust_mode=EligibilityTrustMode.SYNTHETIC_D15_HARNESS,
        assessment_key=assessment_key,
        idempotency_key=idempotency_key,
        items=items,
        catalog_key=catalog_key,
        harness_attestation=attestation,
        performance_mode=performance_mode,
    )