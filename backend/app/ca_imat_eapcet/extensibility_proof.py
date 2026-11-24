from __future__ import annotations

from pathlib import Path

from app.ca_imat_eapcet.constants import EAPCET_PACK_CODE, IMAT_PACK_CODE
from app.ca_imat_eapcet.contracts import AllocateRequest, ExtensibilityProof
from app.ca_imat_eapcet.enums import (
    Day14ProfileKind,
    Day14SourceTrustMode,
    EapcetStream,
    PlanVerdict,
)
from app.ca_imat_eapcet.practice_service import Day14PracticeService


def _scan_generic_modules_for_eapcet_branches() -> list[str]:
    hits: list[str] = []
    root = Path(__file__).resolve().parents[1]
    patterns = ("eapcet", "EAPCET", EAPCET_PACK_CODE)
    for mod_path in (
        root / "models" / "examination.py",
        root / "jee_advanced" / "planner.py",
        root / "cuet_clat" / "practice_service.py",
    ):
        if not mod_path.exists():
            continue
        text = mod_path.read_text(encoding="utf-8")
        for pat in patterns:
            if pat in text and "examination_family" not in text:
                hits.append(f"{mod_path.name}:{pat}")
    return hits


def exercise_config_driven_onboarding() -> PlanVerdict:
    """Allocate via pack codes only (no EAPCET-specific engine edits)."""

    svc = Day14PracticeService()
    eapcet = svc.allocate(
        AllocateRequest(
            exam_pack_code=EAPCET_PACK_CODE,
            profile_kind=Day14ProfileKind.SYNTHETIC_DEMO,
            trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
            paper_or_section="mathematics",
            requested_count=3,
            academic_year="2026",
            stream=EapcetStream.ENGINEERING,
            topic_code="algebra",
        )
    )
    imat = svc.allocate(
        AllocateRequest(
            exam_pack_code=IMAT_PACK_CODE,
            profile_kind=Day14ProfileKind.SYNTHETIC_DEMO,
            trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
            paper_or_section="biology",
            requested_count=2,
            academic_year="2026",
        )
    )
    if eapcet.delivered_count >= 3 and imat.delivered_count == 2:
        return PlanVerdict.PASS
    return PlanVerdict.NOT_READY


def build_extensibility_proof() -> ExtensibilityProof:
    branches = _scan_generic_modules_for_eapcet_branches()
    demo = exercise_config_driven_onboarding()
    if branches:
        verdict = PlanVerdict.FAIL
    elif demo is PlanVerdict.PASS:
        verdict = PlanVerdict.REVIEW_REQUIRED  # config demo only; not full generic onboarding proof
    else:
        verdict = PlanVerdict.NOT_READY
    return ExtensibilityProof(
        generic_modules_inspected=[
            "app.models.examination",
            "app.cuet_clat.practice_service",
            "app.jee_advanced.planner",
        ],
        eapcet_specific_branches_in_generic=branches,
        pack_config_driven=False,
        verdict=verdict,
    )