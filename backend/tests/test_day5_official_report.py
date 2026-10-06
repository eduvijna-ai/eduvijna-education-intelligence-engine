from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.curriculum_intelligence.scoped_curriculum import ScopeError
from app.day5_official_report import _catalogue_gaps, build_official_report
from app.db.base import Base
from app.repo_paths import curricula_content_dir


@pytest.fixture
def report_session(tmp_path: Path) -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def test_registry_only_manifest_produces_structured_report(
    report_session: Session, tmp_path: Path
) -> None:
    report = build_official_report(report_session, storage_root=tmp_path / "storage")
    assert report["official_source_backed_acceptance"] is False
    assert report["acceptance"]["passed"] is False
    assert isinstance(report["sources"], list) and report["sources"]
    assert report["unresolved_applicability"]
    assert report["catalogue_gaps"]
    assert report["public_artifact_contains"]
    assert "materialization_blockers" in report
    assert "fetch_blockers" in report


def test_scope_error_during_materialization_is_reported_not_raised(
    report_session: Session, tmp_path: Path
) -> None:
    with patch(
        "app.day5_official_report.official_telangana_demonstration",
        side_effect=ScopeError("Scoped curriculum requires retrieved original source bytes"),
    ):
        report = build_official_report(report_session, storage_root=tmp_path / "storage")
    assert report["materialization_status"] == "blocked"
    assert report["materialization_blockers"]
    assert report["materialization_blockers"][0]["error_type"] == "ScopeError"
    assert not report["acceptance"]["passed"]


def test_official_report_json_serializable(report_session: Session, tmp_path: Path) -> None:
    report = build_official_report(report_session, storage_root=tmp_path / "storage")
    json.dumps(report)


def test_day5_verify_official_main_emits_json_without_traceback(tmp_path: Path) -> None:
    import sys

    from app import day5_verify

    with patch.object(
        day5_verify,
        "build_official_report",
        return_value={
            "acceptance": {"passed": False},
            "official_source_backed_acceptance": False,
            "blocked_sources": [],
            "sources": [],
        },
    ):
        with patch.object(sys, "argv", ["day5_verify", "--fetch-official"]):
            with pytest.raises(SystemExit) as exc:
                day5_verify.main()
    assert exc.value.code == 1


def test_scope_file_resolves_in_curricula_content_dir() -> None:
    scope_path = curricula_content_dir() / "day5_scope.json"
    payload = json.loads(scope_path.read_text(encoding="utf-8"))
    assert payload["approved_tasks"]


def test_detailed_slice_cannot_satisfy_full_catalogue_gate() -> None:
    report = {
        "catalogue_inventories": [
            {
                "pack_code": "ts-scert",
                "inventory_kind": "detailed_slice",
                "coverage": {"status": "complete"},
            },
            {
                "pack_code": "tgbie",
                "inventory_kind": "detailed_slice",
                "coverage": {"status": "complete"},
            },
        ]
    }
    gaps = _catalogue_gaps(report)
    assert {item["pack_code"] for item in gaps} == {"ts-scert", "tgbie"}


def test_supplemental_authority_directories_excluded_from_academic_blockers(
    report_session: Session, tmp_path: Path
) -> None:
    report = build_official_report(report_session, storage_root=tmp_path / "storage")
    accounting = report["manifest_accounting"]
    assert accounting["manifest_total"] == 15
    assert accounting["required_academic_count"] == 13
    assert accounting["supplemental_authority_count"] == 2
    directory_keys = {"telangana-state-directory-tgbie", "telangana-higher-education-tgbie"}
    for source in report["sources"]:
        if source["key"] in directory_keys:
            assert source["evidence_role"] == "supplemental_authority"
            assert source["academic_applicability_required"] is False
            assert source["academic_applicability_verified"] is None
    assert not any(
        item["source_key"] in directory_keys for item in report["unresolved_applicability"]
    )
    assert not any(
        item.get("source_key") in directory_keys for item in report["fetch_blockers"]
    )
    assert not any(
        item.get("source_key") in directory_keys for item in report["blocked_sources"]
    )


def test_denied_sources_are_metadata_only_and_per_entry_failure_preserves_success(
    report_session: Session, tmp_path: Path
) -> None:
    from app.curriculum_intelligence.service import load_source_manifest

    entries = load_source_manifest(curricula_content_dir() / "day5_official_sources.json")
    denied = entries[0].model_copy(update={"metadata_json": {"automated_fetch_blocked": True}})
    calls = []

    def register(selected, **kwargs):
        calls.append((selected[0].key, kwargs["fetch_content"]))
        if len(calls) == 2:
            raise ValueError("isolated registration failure")
        return {}

    with (
        patch(
            "app.day5_official_report.load_source_manifest",
            return_value=[denied, entries[1], entries[2]],
        ),
        patch(
            "app.day5_official_report.CurriculumIntelligenceService.ensure_manifest_sources",
            side_effect=register,
        ),
    ):
        report = build_official_report(report_session, storage_root=tmp_path / "storage")
    assert calls == [(denied.key, False), (entries[1].key, True), (entries[2].key, True)]
    assert any(item.get("source_key") == entries[1].key for item in report["fetch_blockers"])
    assert not report["acceptance"]["passed"]
