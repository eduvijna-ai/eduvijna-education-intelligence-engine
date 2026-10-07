"""Tests for Day 5 CI deferral gate (structured report only, no greenwash)."""

from __future__ import annotations

import json
from pathlib import Path

from app.day5_official_ci_gate import (
    _APPROVED_AUTOMATED_FETCH_BLOCKED_KEYS,
    _APPROVED_DEFERRED_PACKAGES,
    _APPROVED_PACK_CODES,
    _APPROVED_REQUIRED_IDENTITIES,
    _APPROVED_REQUIRED_KEYS,
    _APPROVED_SCERT_GRADES,
    _APPROVED_SLICE_KEYS,
    _APPROVED_SUPPLEMENTAL_IDENTITIES,
    _APPROVED_SUPPLEMENTAL_KEYS,
    _APPROVED_TGBIE_YEARS,
    resolve_ci_exit_code,
)

_DEFERRED_STATE = """days:
  5:
    deferred_backlog: D5-DS01
    deferred_backlog_status: DEFERRED_BY_FOUNDER
"""
_DEFERRED_UNRESOLVED = [
    "scert-viii-physical-science-english:official_bytes_unavailable",
    "scert-viii-biological-science-english:official_bytes_unavailable",
    "scert-textbook-catalogue:governing_version_applicability_required",
    (
        "tgbie-pack:governing_syllabus_required;"
        "annual_plans_are_supporting_calendar_evidence"
    ),
]
_STATIC_COMPONENTS = {
    "invalid_required_scope_or_duplicate_evidence",
    "required_catalogue_inventories",
    "invalid_frozen_catalogue_scope",
    "ts-scert_catalogue_scope",
    "tgbie_catalogue_scope",
    "required_official_sources_blocked",
    "fetch_blockers",
    "unresolved_applicability",
    "catalogue_gaps",
    "unresolved_materialization",
}


def _identity_record(identity: tuple[str, str, str, str]) -> dict[str, str]:
    key, url, source_type, document_type = identity
    return {
        "key": key,
        "url": url,
        "source_type": source_type,
        "document_type": document_type,
    }


def _deferred_scope() -> dict:
    return {
        "deferred_authoritative_source_backlog": {
            "id": "D5-DS01",
            "status": "DEFERRED_BY_FOUNDER",
            "evidence_packages": sorted(_APPROVED_DEFERRED_PACKAGES),
        },
        "frozen_required_academic_sources": [
            _identity_record(identity) for identity in sorted(_APPROVED_REQUIRED_IDENTITIES)
        ],
        "frozen_supplemental_authority_sources": [
            _identity_record(identity)
            for identity in sorted(_APPROVED_SUPPLEMENTAL_IDENTITIES)
        ],
        "required_detailed_slices": [
            {
                "key": key,
                "status": "blocked",
                "source_revision": None,
                "academic_version": None,
            }
            for key in sorted(_APPROVED_SLICE_KEYS)
        ],
        "packs": [
            {
                "code": "ts-scert",
                "grades": list(_APPROVED_SCERT_GRADES),
                "academic_version": None,
            },
            {
                "code": "tgbie",
                "years": list(_APPROVED_TGBIE_YEARS),
                "academic_version": None,
            },
        ],
    }


def _source_lookup() -> dict[str, tuple[str, str, str]]:
    records: dict[str, tuple[str, str, str]] = {}
    for key, url, _source_type, document_type in _APPROVED_REQUIRED_IDENTITIES:
        records[key] = (url, document_type, "required_academic")
    for key, url, _source_type, document_type in _APPROVED_SUPPLEMENTAL_IDENTITIES:
        records[key] = (url, document_type, "supplemental_authority")
    return records


def _sound_report() -> dict:
    lookup = _source_lookup()
    required_sources = [
        {
            "key": key,
            "url": lookup[key][0],
            "domain": lookup[key][1],
            "evidence_role": "required_academic",
            "retrieved_content": False,
            "registry_only": True,
            "academic_applicability_required": True,
            "academic_applicability_verified": False,
        }
        for key in sorted(_APPROVED_REQUIRED_KEYS)
    ]
    supplemental_sources = [
        {
            "key": key,
            "url": lookup[key][0],
            "domain": lookup[key][1],
            "evidence_role": "supplemental_authority",
            "retrieved_content": True,
            "registry_only": False,
            "academic_applicability_required": False,
            "academic_applicability_verified": None,
        }
        for key in sorted(_APPROVED_SUPPLEMENTAL_KEYS)
    ]
    components = sorted(_APPROVED_SLICE_KEYS | _STATIC_COMPONENTS)
    fetch_blockers = [
        {
            "stage": "official_retrieval",
            "source_key": key,
            "url": lookup[key][0],
            "reason": "Automated retrieval denied; manual official upload required",
        }
        for key in sorted(_APPROVED_AUTOMATED_FETCH_BLOCKED_KEYS)
    ]
    return {
        "status": "blocked_or_review_required",
        "official_source_backed_acceptance": False,
        "acceptance": {
            "passed": False,
            "incomplete_components": components,
        },
        "manifest_identity_blockers": [],
        "manifest_classification_blockers": [],
        "materialization_blockers": [],
        "supplemental_retrieval": [],
        "materialized_slices": [],
        "extracted_slices": [],
        "catalogue_inventories": [],
        "materialization_status": "attempted",
        "queries": {},
        "manifest_accounting": {
            "manifest_total": 15,
            "manifest_validated_distinct": 15,
            "required_academic_expected_count": 13,
            "required_academic_present_count": 13,
            "required_academic_count": 13,
            "supplemental_authority_count": 2,
            "required_academic_retrieved": 0,
            "required_academic_registry_only": 13,
            "supplemental_authority_retrieved": 2,
            "supplemental_authority_registry_only": 0,
        },
        "sources": required_sources + supplemental_sources,
        "fetch_blockers": fetch_blockers,
        "unresolved_applicability": [
            {
                "source_key": key,
                "url": lookup[key][0],
                "reason": (
                    "No governing applicability notice verified from exact source bytes"
                ),
            }
            for key in sorted(_APPROVED_REQUIRED_KEYS)
        ],
        "catalogue_gaps": [
            {
                "pack_code": code,
                "reason": "No complete official catalogue inventory materialized",
            }
            for code in sorted(_APPROVED_PACK_CODES)
        ],
        "unresolved_materialization": list(_DEFERRED_UNRESOLVED),
        "public_artifact_contains": "metadata only",
    }


def _resolve(
    tmp_path: Path,
    payload: dict | None = None,
    *,
    verifier_exit: int = 1,
    state_text: str = _DEFERRED_STATE,
    scope: dict | None = None,
) -> int:
    report = tmp_path / "report.json"
    report.write_text(json.dumps(payload or _sound_report()), encoding="utf-8")
    state = tmp_path / "state.yml"
    state.write_text(state_text, encoding="utf-8")
    scope_path = tmp_path / "scope.json"
    scope_path.write_text(json.dumps(scope or _deferred_scope()), encoding="utf-8")
    return resolve_ci_exit_code(
        verifier_exit,
        report,
        execution_state_path=state,
        scope_path=scope_path,
    )


def test_contract_is_pinned_to_thirteen_plus_two() -> None:
    assert len(_APPROVED_REQUIRED_IDENTITIES) == 13
    assert len(_APPROVED_REQUIRED_KEYS) == 13
    assert len(_APPROVED_SUPPLEMENTAL_IDENTITIES) == 2
    assert len(_APPROVED_SUPPLEMENTAL_KEYS) == 2


def test_verified_success_requires_matching_report(tmp_path: Path) -> None:
    payload = _sound_report()
    payload["status"] = "official_source_backed"
    payload["official_source_backed_acceptance"] = True
    payload["acceptance"] = {"passed": True, "incomplete_components": []}
    assert _resolve(tmp_path, payload, verifier_exit=0) == 0
    assert _resolve(tmp_path, _sound_report(), verifier_exit=0) == 1


def test_deferred_structured_fail_closed_softens_ci_only(tmp_path: Path) -> None:
    assert _resolve(tmp_path) == 0


def test_crash_empty_report_fails_ci(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text("", encoding="utf-8")
    state = tmp_path / "state.yml"
    state.write_text(_DEFERRED_STATE, encoding="utf-8")
    scope = tmp_path / "scope.json"
    scope.write_text(json.dumps(_deferred_scope()), encoding="utf-8")
    assert resolve_ci_exit_code(
        1,
        report,
        execution_state_path=state,
        scope_path=scope,
    ) == 1


def test_malformed_json_fails_ci(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text("not json", encoding="utf-8")
    state = tmp_path / "state.yml"
    state.write_text(_DEFERRED_STATE, encoding="utf-8")
    scope = tmp_path / "scope.json"
    scope.write_text(json.dumps(_deferred_scope()), encoding="utf-8")
    assert resolve_ci_exit_code(
        1,
        report,
        execution_state_path=state,
        scope_path=scope,
    ) == 1


def test_identity_blockers_fail_ci_even_when_deferred(tmp_path: Path) -> None:
    payload = _sound_report()
    payload["manifest_identity_blockers"] = [{"key": "dup"}]
    assert _resolve(tmp_path, payload) == 1


def test_deferral_must_be_under_day_five(tmp_path: Path) -> None:
    misplaced = """days:
  5: {}
  6:
    deferred_backlog: D5-DS01
    deferred_backlog_status: DEFERRED_BY_FOUNDER
"""
    assert _resolve(tmp_path, state_text=misplaced) == 1


def test_comment_strings_do_not_authorize_deferral(tmp_path: Path) -> None:
    comments_only = """# deferred_backlog: D5-DS01
# deferred_backlog_status: DEFERRED_BY_FOUNDER
days:
  5: {}
"""
    assert _resolve(tmp_path, state_text=comments_only) == 1


def test_registration_error_cannot_be_deferred(tmp_path: Path) -> None:
    payload = _sound_report()
    payload["fetch_blockers"].append(
        {
            "stage": "manifest_registration",
            "source_key": "scert-syllabus-index",
            "reason": "database failure",
            "error_type": "RuntimeError",
        }
    )
    assert _resolve(tmp_path, payload) == 1


def test_materialization_error_cannot_be_deferred(tmp_path: Path) -> None:
    payload = _sound_report()
    payload["materialization_blockers"] = [
        {"error_type": "AttributeError", "reason": "programming defect"}
    ]
    assert _resolve(tmp_path, payload) == 1


def test_unexpected_acceptance_component_cannot_be_deferred(tmp_path: Path) -> None:
    payload = _sound_report()
    payload["acceptance"]["incomplete_components"].append(
        "unexpected_engineering_failure"
    )
    assert _resolve(tmp_path, payload) == 1


def test_partial_required_retrieval_requires_new_review(tmp_path: Path) -> None:
    payload = _sound_report()
    payload["manifest_accounting"]["required_academic_retrieved"] = 1
    payload["manifest_accounting"]["required_academic_registry_only"] = 12
    first_required = next(
        item for item in payload["sources"] if item["evidence_role"] == "required_academic"
    )
    first_required["retrieved_content"] = True
    first_required["registry_only"] = False
    assert _resolve(tmp_path, payload) == 1


def test_supplemental_retrieval_failure_cannot_be_deferred(tmp_path: Path) -> None:
    payload = _sound_report()
    payload["supplemental_retrieval"] = [{"reason": "network failure"}]
    assert _resolve(tmp_path, payload) == 1


def test_required_manifest_cannot_shrink(tmp_path: Path) -> None:
    scope = _deferred_scope()
    scope["frozen_required_academic_sources"].pop()
    assert _resolve(tmp_path, scope=scope) == 1


def test_required_manifest_identity_cannot_be_replaced(tmp_path: Path) -> None:
    scope = _deferred_scope()
    scope["frozen_required_academic_sources"][0]["url"] = "https://example.invalid/replaced"
    assert _resolve(tmp_path, scope=scope) == 1


def test_supplemental_manifest_cannot_shrink(tmp_path: Path) -> None:
    scope = _deferred_scope()
    scope["frozen_supplemental_authority_sources"].pop()
    assert _resolve(tmp_path, scope=scope) == 1


def test_deferred_slice_set_cannot_shrink(tmp_path: Path) -> None:
    scope = _deferred_scope()
    scope["required_detailed_slices"].pop()
    assert _resolve(tmp_path, scope=scope) == 1


def test_deferred_evidence_packages_cannot_change(tmp_path: Path) -> None:
    scope = _deferred_scope()
    scope["deferred_authoritative_source_backlog"]["evidence_packages"].pop()
    assert _resolve(tmp_path, scope=scope) == 1


def test_report_source_identity_cannot_change(tmp_path: Path) -> None:
    payload = _sound_report()
    payload["sources"][0]["url"] = "https://example.invalid/replaced"
    assert _resolve(tmp_path, payload) == 1
