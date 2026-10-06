from __future__ import annotations

import pytest

from app.curriculum_intelligence.day5_manifest_evidence import manifest_evidence_role
from app.curriculum_intelligence.source_domains import require_domain, source_domain
from app.models.enums import SourceType
from app.schemas.curriculum_intelligence import OfficialSourceManifestEntry


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


def test_authority_directory_is_supplemental_only() -> None:
    entry = _entry(
        key="dir",
        document_type="authority_directory",
        metadata_json={"governing_curriculum_membership": False},
    )
    assert manifest_evidence_role(entry) == "supplemental_authority"
    snapshot = {
        "metadata_json": {"document_type": "authority_directory"},
    }
    assert source_domain(snapshot) == "authority_reference"
    with pytest.raises(ValueError, match="cannot establish membership"):
        require_domain(snapshot, "membership")


def test_syllabus_cannot_bypass_via_governing_curriculum_membership_false() -> None:
    entry = _entry(
        metadata_json={"governing_curriculum_membership": False},
        document_type="subject_syllabus",
    )
    assert manifest_evidence_role(entry) == "required_academic"


def test_catalogue_index_remains_required_academic() -> None:
    entry = _entry(
        document_type="textbook_index",
        metadata_json={"governing_curriculum_membership": False, "publication_status": "draft"},
    )
    assert manifest_evidence_role(entry) == "required_academic"


def test_conflicting_authority_directory_domain_fails_closed() -> None:
    entry = _entry(
        key="fraud",
        document_type="authority_directory",
        metadata_json={"source_domain": "syllabus"},
    )
    with pytest.raises(ValueError, match="conflicting"):
        manifest_evidence_role(entry)
