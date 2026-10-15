from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.day7_verify import build_verification_report
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.knowledge_intelligence.governance import verify_day7_governance_state


def _fixtures_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures"


def test_governance_active_day7_passes() -> None:
    fixture = _fixtures_dir() / "execution-state-day7-governance.yml"
    report = verify_day7_governance_state(explicit_path=fixture)
    assert report["passed"] is True
    checks = report["checks"]
    assert checks["mode"] == "active_day7"
    assert checks["day8_locked"] is True


def test_governance_historical_day8_regression_passes() -> None:
    fixture = _fixtures_dir() / "execution-state-day8-historical-day7.yml"
    report = verify_day7_governance_state(explicit_path=fixture)
    assert report["passed"] is True
    checks = report["checks"]
    assert checks["mode"] == "historical_day7_regression"
    assert checks["day7_complete"] is True
    assert checks["day7_founder_approved"] is True
    assert checks["day8_legitimate_progress"] is True
    assert "day8_locked" not in checks


def test_governance_fails_when_day8_active_but_day7_incomplete() -> None:
    fixture = _fixtures_dir() / "execution-state-invalid-day8-active-day7-incomplete.yml"
    report = verify_day7_governance_state(explicit_path=fixture)
    assert report["passed"] is False
    assert report["checks"]["mode"] == "historical_day7_regression"
    assert report["checks"]["day7_complete"] is False


def test_governance_fails_when_day7_complete_without_founder_approval() -> None:
    fixture = _fixtures_dir() / "execution-state-invalid-day7-complete-unapproved.yml"
    report = verify_day7_governance_state(explicit_path=fixture)
    assert report["passed"] is False
    assert report["checks"]["day7_founder_approved"] is False


def test_governance_fails_when_day8_still_locked_at_day8() -> None:
    fixture = _fixtures_dir() / "execution-state-invalid-day8-still-locked.yml"
    report = verify_day7_governance_state(explicit_path=fixture)
    assert report["passed"] is False
    assert report["checks"]["day8_legitimate_progress"] is False


def test_governance_d5_ds01_mutation_fails_in_active_day7_mode() -> None:
    fixture = _fixtures_dir() / "execution-state-day7-active-d5-mutated.yml"
    report = verify_day7_governance_state(explicit_path=fixture)
    assert report["passed"] is False
    assert report["checks"]["mode"] == "active_day7"
    assert report["checks"]["d5_ds01_deferred"] is False


def test_governance_d5_ds01_mutation_fails_in_historical_mode() -> None:
    fixture = _fixtures_dir() / "execution-state-day8-historical-d5-mutated.yml"
    report = verify_day7_governance_state(explicit_path=fixture)
    assert report["passed"] is False
    assert report["checks"]["mode"] == "historical_day7_regression"
    assert report["checks"]["d5_ds01_issue_16"] is False


def test_day7_verify_passes_on_legitimate_day8_execution_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixtures_dir() / "execution-state-day8-historical-day7.yml"
    monkeypatch.setenv("EDUVIJNA_EXECUTION_STATE_PATH", str(fixture))
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        report = build_verification_report(session)
    assert report["checks"]["day7_governance_valid"] is True
    assert report["governance"]["checks"]["mode"] == "historical_day7_regression"
    assert report["passed"] is True
