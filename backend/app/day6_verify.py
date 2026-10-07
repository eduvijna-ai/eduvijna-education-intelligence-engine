"""Founder Day 6 verification harness (D6-35)."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.education_intelligence.contracts import InstitutionPolicyOverride
from app.education_intelligence.enums import ValidationStatus
from app.education_intelligence.fixtures import (
    adversarial_broken_rubric,
    adversarial_cognitive_mismatch,
    adversarial_invalid_progression,
    adversarial_safety_trigger,
    adversarial_wrong_lo_version,
    positive_cbse_item,
    seed_cbse_fixture_curriculum,
    seed_telangana_fixture_curriculum,
)
from app.education_intelligence.service import EducationIntelligenceValidationService


def _git_head() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2]
            )
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def build_verification_report(session: Session) -> dict[str, object]:
    cbse = seed_cbse_fixture_curriculum(session)
    tg = seed_telangana_fixture_curriculum(session)
    session.commit()
    service = EducationIntelligenceValidationService(session)

    valid = service.validate_item(positive_cbse_item(cbse), board_code="cbse")
    wrong_lo = service.validate_item(adversarial_wrong_lo_version(cbse), board_code="cbse")
    cog_mismatch = service.validate_item(adversarial_cognitive_mismatch(cbse), board_code="cbse")
    rubric_bad = service.validate_item(adversarial_broken_rubric(cbse), board_code="cbse")
    safety = service.validate_item(adversarial_safety_trigger(cbse), board_code="cbse")
    progression_bad = service.validate_item(
        adversarial_invalid_progression(cbse), board_code="cbse"
    )
    progression_only = service.validate_cognitive_progression(["remember", "understand", "apply"])

    weaken_override = InstitutionPolicyOverride(
        institution_id="inst-a",
        policy_key="quality.explanation_when_required",
        value={"disable_blocking": True},
        tightens_only=True,
    )
    policy_weaken_item = positive_cbse_item(cbse).model_copy(
        update={
            "item_id": "policy-weaken",
            "institution_id": "inst-a",
            "explanation_required": True,
            "explanation_present": False,
        }
    )
    with_weaken = service.validate_item(
        policy_weaken_item,
        board_code="cbse",
        institution_overrides=[weaken_override],
    )

    isolation_item = positive_cbse_item(cbse).model_copy(
        update={
            "item_id": "tenant-isolation",
            "institution_id": "inst-a",
            "metadata_json": {"simulate_cross_tenant_override_leak": True},
        }
    )
    foreign_override = InstitutionPolicyOverride(
        institution_id="inst-b",
        policy_key="quality.explanation_when_required",
        value={"disable_blocking": True},
    )
    isolation = service.validate_item(
        isolation_item,
        board_code="cbse",
        institution_overrides=[foreign_override],
    )

    tg_item = positive_cbse_item(tg).model_copy(
        update={
            "item_id": "tg-positive",
            "learning_outcome_ids": [tg["learning_outcome_id"]],
            "curriculum_version_id": tg["curriculum_version_id"],
            "subject_code": tg["subject_code"],
            "metadata_json": {"synthetic_fixture": True, "scope": "telangana"},
        }
    )
    tg_valid = service.validate_item(tg_item, board_code="tg")

    persisted = service.validate_item(positive_cbse_item(cbse), board_code="cbse", persist=True)
    audit = service.get_audit_run(persisted.run_id)

    checks = {
        "valid_item_passes": valid.aggregate_status == ValidationStatus.PASS,
        "wrong_lo_or_version_fails": wrong_lo.aggregate_status == ValidationStatus.FAIL,
        "cognition_mismatch_detected": any(
            "COG-TGT" in code for r in cog_mismatch.results for code in r.rule_codes
        ),
        "difficulty_evidence_visible": any(
            r.validator_id == "difficulty_profile" and r.observed.get("profile")
            for r in valid.results
        ),
        "age_grade_pass_or_review": any(
            r.validator_id == "age_grade_appropriateness"
            and r.status in {ValidationStatus.PASS, ValidationStatus.REVIEW_REQUIRED}
            for r in valid.results
        ),
        "invalid_rubric_fails": rubric_bad.aggregate_status == ValidationStatus.FAIL,
        "official_policy_not_weakened_by_override": with_weaken.aggregate_status
        == ValidationStatus.FAIL,
        "institution_isolation": isolation.aggregate_status == ValidationStatus.FAIL,
        "safety_bias_trigger": safety.blocking_failure,
        "cognitive_progression_invalid_fails": progression_bad.aggregate_status
        == ValidationStatus.FAIL,
        "cognitive_progression_valid_passes": progression_only.aggregate_status
        == ValidationStatus.PASS,
        "provenance_versions_present": bool(valid.taxonomy_version and valid.policy_version),
        "audit_history_persisted": audit is not None,
        "telangana_fixture_runs": tg_valid.run_id,
        "d5_ds01_unchanged": "deferred",
    }

    return {
        "day": 6,
        "head_sha": _git_head(),
        "checks": checks,
        "passed": all(
            v is True
            for k, v in checks.items()
            if k not in {"telangana_fixture_runs", "d5_ds01_unchanged"}
        ),
        "sample_run": {
            "run_id": valid.run_id,
            "taxonomy_version": valid.taxonomy_version,
            "policy_version": valid.policy_version,
            "aggregate_status": valid.aggregate_status.value,
            "explanations": valid.explanations[:5],
        },
    }


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        report = build_verification_report(session)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
