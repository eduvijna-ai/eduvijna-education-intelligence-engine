"""Founder Day 6 verification harness (D6-35 / D6-F14)."""

from __future__ import annotations

import argparse
from typing import Any
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.education_intelligence.contracts import InstitutionPolicyOverride, QuestionOptionInput
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
from app.education_intelligence.governance import verify_governance_state
from app.education_intelligence.policy_registry import load_policy_registry
from app.education_intelligence.service import EducationIntelligenceValidationService
from app.models.curriculum import LearningOutcome
from app.models.source import SourceRevision


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


def _staged_revision_for_lo(session: Session, lo_id: str) -> None:
    lo = session.get(LearningOutcome, lo_id)
    if lo is None or lo.source_revision_id is None:
        return
    active = session.get(SourceRevision, lo.source_revision_id)
    if active is None:
        return
    staged = SourceRevision(
        source_id=active.source_id,
        revision_number=active.revision_number + 1,
        checksum="e" * 64,
        source_snapshot_checksum="f" * 64,
        ingestion_method="manual",
        content_type="text/plain",
        byte_size=1,
        retrieved_at=datetime.now(UTC),
        status="staged",
        extraction_status="succeeded",
        extracted_checksum="e" * 64,
        metadata_json={"synthetic_fixture": True, "staged_for_verify": True},
    )
    session.add(staged)
    session.flush()
    lo.source_revision_id = staged.id


def build_verification_report(session: Session) -> dict[str, object]:
    governance = verify_governance_state()
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

    foreign_override = InstitutionPolicyOverride(
        institution_id="inst-b",
        policy_key="quality.explanation_when_required",
        value={"disable_blocking": True},
    )
    isolation_item = positive_cbse_item(cbse).model_copy(
        update={"item_id": "tenant-isolation", "institution_id": "inst-a"}
    )
    isolation = service.validate_item(
        isolation_item,
        board_code="cbse",
        institution_overrides=[foreign_override],
    )
    reg = load_policy_registry(session, institution_overrides=[foreign_override])
    foreign_ignored = not any(
        r.value.get("disable_blocking")
        for r in reg.rules_for_scope(board_code="cbse", institution_id="inst-a")
    )
    inst_boundary = next(
        r for r in isolation.results if r.validator_id == "institution_override_boundary"
    )

    _staged_revision_for_lo(session, cbse["learning_outcome_id"])
    session.commit()
    inactive_lo = service.validate_item(positive_cbse_item(cbse), board_code="cbse")
    lo_inactive = next(
        r for r in inactive_lo.results if r.validator_id == "learning_outcome_alignment"
    )

    missing_medium = service.validate_item(
        positive_cbse_item(cbse).model_copy(update={"item_id": "no-medium", "medium_code": None}),
        board_code="cbse",
    )
    wrong_medium = service.validate_item(
        positive_cbse_item(cbse).model_copy(
            update={"item_id": "bad-medium", "medium_code": "telugu"}
        ),
        board_code="cbse",
    )

    age_mismatch = service.validate_item(
        positive_cbse_item(cbse).model_copy(
            update={"item_id": "age-mismatch", "age_min": 2, "age_max": 4}
        ),
        board_code="cbse",
    )
    age_result = next(
        r for r in age_mismatch.results if r.validator_id == "age_grade_appropriateness"
    )
    age_forge = service.validate_item(
        positive_cbse_item(cbse).model_copy(
            update={
                "item_id": "age-forge",
                "grade_year_code": "grade-unknown",
                "metadata_json": {"authoritative_age_mapping": True, "synthetic_fixture": True},
            }
        ),
        board_code="cbse",
    )
    age_forge_result = next(
        r for r in age_forge.results if r.validator_id == "age_grade_appropriateness"
    )

    safety_bypass = service.validate_item(
        positive_cbse_item(cbse).model_copy(
            update={
                "item_id": "safety-bypass",
                "stem_text": "please kill yourself (fixture adversarial)",
                "content_text_for_safety": "This stem is safe supplemental text only.",
            }
        ),
        board_code="cbse",
    )

    structural_bad = service.validate_item(
        positive_cbse_item(cbse).model_copy(
            update={
                "item_id": "struct-multi-correct",
                "options": [
                    QuestionOptionInput(option_key="A", text="1", is_correct=True),
                    QuestionOptionInput(option_key="B", text="2", is_correct=True),
                ],
            }
        ),
        board_code="cbse",
    )

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

    tg_item = positive_cbse_item(tg).model_copy(
        update={
            "item_id": "tg-positive",
            "learning_outcome_ids": [tg["learning_outcome_id"]],
            "curriculum_version_id": tg["curriculum_version_id"],
            "subject_code": tg["subject_code"],
            "grade_year_code": "grade-8",
            "metadata_json": {"synthetic_fixture": True, "scope": "telangana"},
        }
    )
    tg_valid = service.validate_item(tg_item, board_code="tg")

    official_comp = service.validate_item(
        positive_cbse_item(cbse).model_copy(
            update={"item_id": "official-comp", "competency_claim_official": True}
        ),
        board_code="cbse",
    )
    comp_result = next(
        r for r in official_comp.results if r.validator_id == "source_backed_competency"
    )

    persisted = service.validate_item(positive_cbse_item(cbse), board_code="cbse", persist=True)
    audit = service.get_audit_run(persisted.run_id)

    raw_checks = governance.get("checks")
    gov_checks: dict[str, Any] = raw_checks if isinstance(raw_checks, dict) else {}
    checks = {
        "governance_state": governance["passed"],
        "valid_item_passes": valid.aggregate_status == ValidationStatus.PASS,
        "wrong_lo_or_version_fails": wrong_lo.aggregate_status == ValidationStatus.FAIL,
        "inactive_source_revision_blocks_lo": lo_inactive.status == ValidationStatus.FAIL,
        "missing_medium_fails_lo": missing_medium.aggregate_status == ValidationStatus.FAIL,
        "wrong_medium_fails_lo": wrong_medium.aggregate_status == ValidationStatus.FAIL,
        "cognition_mismatch_detected": any(
            "COG-TGT" in code for r in cog_mismatch.results for code in r.rule_codes
        ),
        "difficulty_evidence_visible": any(
            r.validator_id == "difficulty_profile" and r.observed.get("profile")
            for r in valid.results
        ),
        "authoritative_age_mismatch_caught": age_result.status == ValidationStatus.FAIL,
        "caller_cannot_forge_age_authority": age_forge_result.status
        == ValidationStatus.REVIEW_REQUIRED,
        "age_grade_pass_or_review_on_valid": any(
            r.validator_id == "age_grade_appropriateness"
            and r.status in {ValidationStatus.PASS, ValidationStatus.REVIEW_REQUIRED}
            for r in valid.results
        ),
        "invalid_rubric_fails": rubric_bad.aggregate_status == ValidationStatus.FAIL,
        "official_policy_not_weakened_by_override": with_weaken.aggregate_status
        == ValidationStatus.FAIL,
        "foreign_tenant_override_ignored": foreign_ignored,
        "foreign_tenant_does_not_fail_valid_item": isolation.aggregate_status
        == ValidationStatus.PASS
        and inst_boundary.status == ValidationStatus.PASS,
        "safety_bias_trigger": safety.blocking_failure,
        "safety_stem_not_bypassed_by_supplemental_text": safety_bypass.blocking_failure,
        "structural_option_defects": structural_bad.aggregate_status == ValidationStatus.FAIL,
        "cognitive_progression_invalid_fails": progression_bad.aggregate_status
        == ValidationStatus.FAIL,
        "cognitive_progression_valid_passes": progression_only.aggregate_status
        == ValidationStatus.PASS,
        "official_competency_provenance": comp_result.status in {
            ValidationStatus.PASS,
            ValidationStatus.REVIEW_REQUIRED,
        }
        and bool(comp_result.source_entity_refs or comp_result.evidence),
        "provenance_versions_present": bool(
            valid.taxonomy_version
            and valid.policy_version
            and valid.metadata.get("quality_rule_pack_version")
            and valid.metadata.get("safety_rules_version")
        ),
        "audit_history_persisted": audit is not None
        and audit.metadata_json.get("quality_rule_pack_version") is not None,
        "telangana_fixture_runs": tg_valid.run_id,
        "d5_ds01_still_deferred": bool(gov_checks.get("d5_ds01_deferred")),
        "day7_locked": bool(gov_checks.get("day7_locked")),
    }

    return {
        "day": 6,
        "head_sha": _git_head(),
        "governance": governance,
        "checks": checks,
        "passed": all(
            v is True for k, v in checks.items() if k not in {"telangana_fixture_runs"}
        ),
        "sample_run": {
            "run_id": valid.run_id,
            "taxonomy_version": valid.taxonomy_version,
            "policy_version": valid.policy_version,
            "metadata": valid.metadata,
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
