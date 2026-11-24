"""F04-A: contracts for CLAT current affairs evidence preflight (read-only)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.cuet_clat.constants import CLAT_PACK_CODE

CLAT_CA_SECTION_CODE = "current_affairs_gk"
SYNTHETIC_CA_FIXTURE_METADATA_KEY = "d13_f04a_synthetic_current_affairs_fixture"
F04A_PERSISTED_LOCATOR_KEY = "f04a_persisted_locator"
F04A_FIXTURE_FACT_DATE_KEY = "f04a_fixture_fact_date"
F04A_FIXTURE_BYTE_SHA_KEY = "f04a_fixture_byte_sha256"
F04A_FIXTURE_BYTE_SIZE_KEY = "f04a_fixture_byte_size"
F04A_BINDING_HASH_VERSION = "f04a-claim-binding@v2"
F04A_HARNESS_TOKEN = "d13-f04a-ca-evidence-harness-v1"


class ClatEvidenceOperatingMode(StrEnum):
    SYNTHETIC_TEST_ONLY = "synthetic_test_only"
    OFFICIAL_CLAT_2027 = "official_clat_2027"


class ClatEvidencePreflightVerdict(StrEnum):
    SOURCE_PENDING = "source_pending"
    FAIL = "fail"
    REVIEW_REQUIRED = "review_required"
    MECHANICAL_DEMO_OK = "mechanical_demo_ok"


class ClatEvidenceIssueCode(StrEnum):
    NO_EVIDENCE = "d13.f04a.no_evidence"
    MANIFEST_ONLY = "d13.f04a.manifest_discovery_only"
    MISSING_SOURCE = "d13.f04a.missing_source"
    MISSING_REVISION = "d13.f04a.missing_revision"
    REVISION_NOT_ACTIVE = "d13.f04a.revision_not_active"
    CHECKSUM_MISMATCH = "d13.f04a.checksum_mismatch"
    BINDING_MISSING = "d13.f04a.binding_missing"
    BINDING_INACTIVE = "d13.f04a.binding_inactive"
    BINDING_IDENTITY_MISMATCH = "d13.f04a.binding_identity_mismatch"
    RIGHTS_NOT_APPROVED = "d13.f04a.rights_not_approved"
    CURATOR_NOT_APPROVED = "d13.f04a.curator_not_approved"
    UNAPPROVED_TRUST_TIER = "d13.f04a.unapproved_trust_tier"
    NON_OFFICIAL_FOR_OFFICIAL_MODE = "d13.f04a.non_official_source"
    SYNTHETIC_FOR_OFFICIAL_MODE = "d13.f04a.synthetic_denied_official"
    EXAM_SCOPE_MISMATCH = "d13.f04a.exam_scope_mismatch"
    SECTION_UNSUPPORTED = "d13.f04a.section_unsupported"
    TENANT_MISMATCH = "d13.f04a.tenant_mismatch"
    BINDING_TENANT_MISMATCH = "d13.f04a.binding_tenant_mismatch"
    MISSING_TRUSTED_SCOPE = "d13.f04a.missing_trusted_scope"
    FACT_DATE_MISSING = "d13.f04a.fact_date_missing"
    FACT_DATE_FUTURE = "d13.f04a.fact_date_future"
    FACT_DATE_STALE = "d13.f04a.fact_date_stale"
    FIXTURE_RECEIPT_MISMATCH = "d13.f04a.fixture_receipt_mismatch"
    CONFLICTING_REVISION = "d13.f04a.conflicting_revision"
    FORGED_CITATION = "d13.f04a.forged_citation"
    LOCATOR_MISMATCH = "d13.f04a.locator_mismatch"
    EXAM_VERSION_UNASSOCIATED = "d13.f04a.exam_version_unassociated"
    CLAIM_BINDING_STALE = "d13.f04a.claim_binding_stale"
    UNTRUSTED_RETRIEVAL_ONLY = "d13.f04a.untrusted_retrieval_only"
    HARNESS_UNAUTHORIZED = "d13.f04a.harness_unauthorized"
    NAIVE_AS_OF = "d13.f04a.naive_as_of"


class ClatCurrentAffairsFreshnessPolicy(BaseModel):
    """Test-injectable freshness window; not an official Consortium rule."""

    max_age_days: int = Field(default=30, ge=1, le=3650)
    policy_label: str = "d13_f04a_synthetic_test_freshness_only"


class ClatCurrentAffairsPreflightRequest(BaseModel):
    exam_family: str = "clat_ug"
    exam_pack_code: str = CLAT_PACK_CODE
    academic_year: str = "2027"
    section_code: str = CLAT_CA_SECTION_CODE
    operating_mode: ClatEvidenceOperatingMode
    claim_text: str = Field(min_length=1, max_length=4000)
    fact_date: date | None = None
    as_of: datetime
    organization_id: str | None = None
    institution_id: str | None = None
    actor_id: str | None = None
    exam_version_id: str | None = None
    retrieval_profile_version: str = "d13-f04a-test-profile@v1"
    freshness_policy: ClatCurrentAffairsFreshnessPolicy = Field(
        default_factory=ClatCurrentAffairsFreshnessPolicy
    )
    expected_claim_binding_hash: str | None = None
    harness_authorized: bool = False
    trusted_harness_token: str | None = None


class ClatCurrentAffairsEvidenceDecision(BaseModel):
    verdict: ClatEvidencePreflightVerdict
    operating_mode: ClatEvidenceOperatingMode
    issue_codes: list[ClatEvidenceIssueCode] = Field(default_factory=list)
    eligible_test_evidence_count: int = 0
    officially_verified_claim_count: int = 0
    mechanical_evidence_checks_ok: bool = False
    factual_claim_independently_verified: bool = False
    official_source_approved: bool = False
    claim_binding_hash: str = ""
    metadata_json: dict[str, object] = Field(default_factory=dict)


def _normalize_claim(claim_text: str) -> str:
    return " ".join(claim_text.split())


def snippet_content_digest(snippet: str) -> tuple[str, int]:
    body = snippet.encode("utf-8")
    return hashlib.sha256(body).hexdigest(), len(body)


def build_claim_scope_grouping_key(
    *,
    claim_text: str,
    organization_id: str,
    institution_id: str,
    exam_version_id: str,
    exam_pack_code: str,
    academic_year: str,
    section_code: str,
) -> str:
    """Canonical scope key for conflict grouping — excludes revision/snippet identity."""

    payload = {
        "claim": _normalize_claim(claim_text),
        "organization_id": organization_id,
        "institution_id": institution_id,
        "exam_version_id": exam_version_id,
        "exam_pack_code": exam_pack_code,
        "academic_year": academic_year,
        "section_code": section_code,
        "grouping_version": "f04a-scope-group@v1",
    }
    raw = json.dumps(payload, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()[:40]


def build_claim_evidence_binding_hash(
    *,
    claim_text: str,
    source_id: str,
    source_revision_id: str,
    source_revision_checksum: str,
    source_snapshot_checksum: str,
    binding_id: str,
    locator: str,
    document_id: str,
    workspace: str,
    snippet_sha256: str,
    snippet_byte_length: int,
    fact_date: date | None,
    as_of_utc: datetime,
    freshness_policy_label: str,
    retrieval_profile_version: str,
    organization_id: str,
    institution_id: str,
    exam_version_id: str,
    exam_pack_code: str,
    academic_year: str,
    section_code: str,
) -> str:
    as_of_norm = as_of_utc.astimezone(UTC)
    payload = {
        "binding_hash_version": F04A_BINDING_HASH_VERSION,
        "claim": _normalize_claim(claim_text),
        "source_id": source_id,
        "source_revision_id": source_revision_id,
        "checksum": source_revision_checksum,
        "source_snapshot_checksum": source_snapshot_checksum,
        "binding_id": binding_id,
        "locator": locator.strip(),
        "document_id": document_id.strip(),
        "workspace": workspace.strip(),
        "snippet_sha256": snippet_sha256,
        "snippet_byte_length": snippet_byte_length,
        "fact_date": fact_date.isoformat() if fact_date else None,
        "as_of_utc": as_of_norm.isoformat(),
        "freshness_policy_label": freshness_policy_label,
        "retrieval_profile_version": retrieval_profile_version,
        "organization_id": organization_id,
        "institution_id": institution_id,
        "exam_version_id": exam_version_id,
        "exam_pack_code": exam_pack_code,
        "academic_year": academic_year,
        "section_code": section_code,
    }
    raw = json.dumps(payload, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()[:40]