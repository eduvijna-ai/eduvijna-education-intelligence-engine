from __future__ import annotations

import json

import pytest

from app.curriculum_intelligence.day5_manifest_evidence import (
    canonical_retrieval_url,
    classify_manifest_entry,
    manifest_evidence_role,
    validate_manifest_identity,
    validate_required_manifest_contract,
)
from app.curriculum_intelligence.source_domains import require_domain, source_domain
from app.models.enums import SourceType
from app.repo_paths import curricula_content_dir
from app.schemas.curriculum_intelligence import OfficialSourceManifestEntry

SCOPE = json.loads((curricula_content_dir() / "day5_scope.json").read_text(encoding="utf-8"))


def _entry(**overrides: object) -> OfficialSourceManifestEntry:
    base = {
        "key": "test-entry",
        "source_type": SourceType.OFFICIAL_AUTHORITY,
        "title": "Test",
        "url": "https://example.invalid/source",
        "authority": "Test Authority",
        "document_type": "subject_syllabus",
        "metadata_json": {},
    }
    base.update(overrides)
    return OfficialSourceManifestEntry.model_validate(base)


def test_frozen_supplemental_directories_match_scope_contract() -> None:
    entry = _entry(
        key="telangana-state-directory-tgbie",
        url="https://www.telangana.gov.in/state-web-directory/",
        document_type="authority_directory",
    )
    assert manifest_evidence_role(entry, SCOPE) == "supplemental_authority"


def test_relabelled_syllabus_stays_required_academic() -> None:
    entry = _entry(
        key="scert-ps-english-syllabus",
        url="https://scert.telangana.gov.in/PDF/publication/syllabus/PS_EM.pdf",
        document_type="authority_directory",
        metadata_json={"governing_curriculum_membership": False},
    )
    role, conflict = classify_manifest_entry(entry, SCOPE)
    assert role == "required_academic"
    assert conflict is not None


def test_relabelled_catalogue_stays_required_academic() -> None:
    entry = _entry(
        key="scert-textbooks-catalogue-2025-26",
        url=(
            "https://www.scert.telangana.gov.in/Home.aspx/Pdf/pdf/"
            "DisplayContent.aspx?encry=ammkNW4%2Fgx+NeApstGPX+A%3D%3D"
        ),
        document_type="authority_directory",
    )
    role, conflict = classify_manifest_entry(entry, SCOPE)
    assert role == "required_academic"
    assert conflict is not None


def test_frozen_supplemental_url_substitution_is_classification_conflict() -> None:
    entry = _entry(
        key="telangana-state-directory-tgbie",
        url="https://example.invalid/substituted",
        document_type="authority_directory",
    )
    role, conflict = classify_manifest_entry(entry, SCOPE)
    assert role == "required_academic"
    assert conflict is not None
    assert "frozen supplemental" in conflict.reason


def test_syllabus_cannot_bypass_via_governing_curriculum_membership_false() -> None:
    entry = _entry(
        metadata_json={"governing_curriculum_membership": False},
        document_type="subject_syllabus",
    )
    assert manifest_evidence_role(entry, SCOPE) == "required_academic"


def test_conflicting_authority_directory_domain_fails_closed() -> None:
    entry = _entry(
        key="telangana-higher-education-tgbie",
        url="https://www.telangana.gov.in/departments/higher-education/",
        document_type="authority_directory",
        metadata_json={"source_domain": "syllabus"},
    )
    role, conflict = classify_manifest_entry(entry, SCOPE)
    assert role == "required_academic"
    assert conflict is not None


def test_duplicate_manifest_key_rejected_before_ingestion() -> None:
    first = _entry(key="dup", url="https://example.invalid/one")
    second = _entry(key="dup", url="https://example.invalid/two")
    validated, blockers = validate_manifest_identity([first, second])
    assert len(validated) == 1
    assert blockers and blockers[0]["reason"] == "Duplicate manifest source key"


def test_duplicate_manifest_url_with_different_keys_rejected() -> None:
    first = _entry(key="one", url="https://example.invalid/same")
    second = _entry(key="two", url="https://example.invalid/same")
    validated, blockers = validate_manifest_identity([first, second])
    assert len(validated) == 1
    assert "URL already bound" in blockers[0]["reason"]


def test_authority_reference_domain_cannot_establish_membership() -> None:
    snapshot = {"metadata_json": {"document_type": "authority_directory"}}
    assert source_domain(snapshot) == "authority_reference"
    with pytest.raises(ValueError, match="cannot establish membership"):
        require_domain(snapshot, "membership")


def test_fragment_equivalent_urls_are_one_retrieval_identity() -> None:
    first = _entry(key="one", url="https://example.invalid/source.pdf#one")
    second = _entry(key="two", url="https://example.invalid/source.pdf#two")
    validated, blockers = validate_manifest_identity([first, second])
    assert len(validated) == 1
    assert blockers
    assert "URL already bound" in blockers[0]["reason"]
    assert canonical_retrieval_url(first.url) == canonical_retrieval_url(second.url)


def test_missing_frozen_required_source_is_contract_blocker() -> None:
    from app.curriculum_intelligence.service import load_source_manifest

    entries = load_source_manifest(curricula_content_dir() / "day5_official_sources.json")
    required_key = SCOPE["frozen_required_academic_sources"][0]["key"]
    reduced = [entry for entry in entries if entry.key != required_key]
    frozen, blockers = validate_required_manifest_contract(reduced, SCOPE)
    assert len(frozen) == 13
    assert any(
        item.get("source_key") == required_key
        and "missing" in str(item.get("reason", "")).lower()
        for item in blockers
    )


def test_malformed_frozen_supplemental_contract_fails_structurally() -> None:
    scope = dict(SCOPE)
    scope["frozen_supplemental_authority_sources"] = [{"key": "broken"}]
    entry = _entry(
        key="telangana-state-directory-tgbie",
        url="https://www.telangana.gov.in/state-web-directory/",
        document_type="authority_directory",
    )
    role, conflict = classify_manifest_entry(entry, scope)
    assert role == "required_academic"
    assert conflict is not None
    assert "missing required field" in conflict.reason
