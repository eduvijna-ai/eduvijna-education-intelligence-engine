"""Tests for Day 5 CI deferral gate (structured report only, no greenwash)."""

from __future__ import annotations

import json
from pathlib import Path

from app.day5_official_ci_gate import resolve_ci_exit_code

_DEFERRED_STATE = """\
days:
  5:
    deferred_backlog: D5-DS01
    deferred_backlog_status: DEFERRED_BY_FOUNDER
"""


def _sound_report() -> dict:
    return {
        "acceptance": {"passed": False, "incomplete_components": ["unresolved_applicability"]},
        "manifest_identity_blockers": [],
        "manifest_classification_blockers": [],
        "manifest_accounting": {
            "required_academic_expected_count": 13,
            "required_academic_present_count": 13,
            "required_academic_count": 13,
            "supplemental_authority_count": 2,
            "manifest_validated_distinct": 15,
        },
        "sources": [{"key": "example"}],
        "public_artifact_contains": "metadata only",
    }


def test_verifier_success_passes(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_sound_report()), encoding="utf-8")
    state = tmp_path / "state.yml"
    state.write_text(_DEFERRED_STATE, encoding="utf-8")
    assert (
        resolve_ci_exit_code(0, report, execution_state_path=state) == 0
    )


def test_deferred_structured_fail_closed_softens_ci_only(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_sound_report()), encoding="utf-8")
    state = tmp_path / "state.yml"
    state.write_text(_DEFERRED_STATE, encoding="utf-8")
    assert (
        resolve_ci_exit_code(1, report, execution_state_path=state) == 0
    )


def test_crash_empty_report_fails_ci(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text("", encoding="utf-8")
    state = tmp_path / "state.yml"
    state.write_text(_DEFERRED_STATE, encoding="utf-8")
    assert resolve_ci_exit_code(1, report, execution_state_path=state) == 1


def test_malformed_json_fails_ci(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text("not json", encoding="utf-8")
    state = tmp_path / "state.yml"
    state.write_text(_DEFERRED_STATE, encoding="utf-8")
    assert resolve_ci_exit_code(1, report, execution_state_path=state) == 1


def test_identity_blockers_fail_ci_even_when_deferred(tmp_path: Path) -> None:
    payload = _sound_report()
    payload["manifest_identity_blockers"] = [{"key": "dup"}]
    report = tmp_path / "report.json"
    report.write_text(json.dumps(payload), encoding="utf-8")
    state = tmp_path / "state.yml"
    state.write_text(_DEFERRED_STATE, encoding="utf-8")
    assert resolve_ci_exit_code(1, report, execution_state_path=state) == 1


def test_without_founder_deferral_fails_ci(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_sound_report()), encoding="utf-8")
    state = tmp_path / "state.yml"
    state.write_text("days:\n  5: {}\n", encoding="utf-8")
    assert resolve_ci_exit_code(1, report, execution_state_path=state) == 1


def test_acceptance_true_never_softens(tmp_path: Path) -> None:
    payload = _sound_report()
    payload["acceptance"]["passed"] = True
    report = tmp_path / "report.json"
    report.write_text(json.dumps(payload), encoding="utf-8")
    state = tmp_path / "state.yml"
    state.write_text(_DEFERRED_STATE, encoding="utf-8")
    assert resolve_ci_exit_code(1, report, execution_state_path=state) == 1
