"""F04-A: contracts for CLAT current affairs evidence preflight (read-only)."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.cuet_clat.constants import CLAT_PACK_CODE

CLAT_CA_SECTION_CODE = "current_affairs_gk"
SYNTHETIC_CA_FIXTURE_METADATA_KEY = "d13_f04a_synthetic_current_affairs_fixture"


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
    FACT_DATE_MISSING = "d13.f04a.fact_date_missing"
    FACT_DATE_FUTURE = "d13.f04a.fact_date_future"
    FACT_DATE_STALE = "d13.f04a.fact_date_stale"
    CONFLICTING_REVISION = "d13.f04a.conflicting_revision"
    FORGED_CITATION = "d13.f04a.forged_citation"
    EXAM_VERSION_UNASSOCIATED = "d13.f04a.exam_version_unassociated"
    CLAIM_BINDING_STALE = "d13.f04a.claim_binding_stale"
    UNTRUSTED_RETRIEVAL_ONLY = "d13.f04a.untrusted_retrieval_only"


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


def build_claim_evidence_binding_hash(
    *,
    claim_text: str,
    source_id: str,
    source_revision_id: str,
    source_revision_checksum: str,
    locator: str,
    document_id: str,
    fact_date: date | None,
    retrieval_profile_version: str,
    exam_pack_code: str,
    academic_year: str,
    section_code: str,
) -> str:
    payload = {
        "claim": " ".join(claim_text.split()),
        "source_id": source_id,
        "source_revision_id": source_revision_id,
        "checksum": source_revision_checksum,
        "locator": locator.strip(),
        "document_id": document_id.strip(),
        "fact_date": fact_date.isoformat() if fact_date else None,
        "retrieval_profile_version": retrieval_profile_version,
        "exam_pack_code": exam_pack_code,
        "academic_year": academic_year,
        "section_code": section_code,
    }
    raw = json.dumps(payload, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()[:40]