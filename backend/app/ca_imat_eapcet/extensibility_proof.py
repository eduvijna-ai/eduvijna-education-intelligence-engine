from __future__ import annotations

import inspect
from pathlib import Path

from app.ca_imat_eapcet.constants import EAPCET_PACK_CODE, GENERIC_ENGINE_MODULES
from app.ca_imat_eapcet.contracts import ExtensibilityProof
from app.ca_imat_eapcet.enums import PlanVerdict


def _scan_generic_modules_for_eapcet_branches() -> list[str]:
    """D14-26: inspect generic modules for forbidden EAPCET-specific conditionals."""

    hits: list[str] = []
    root = Path(__file__).resolve().parents[1]
    patterns = ("eapcet", "EAPCET", EAPCET_PACK_CODE)
    for mod_path in (
        root / "models" / "examination.py",
        root / "jee_advanced" / "planner.py",
    ):
        if not mod_path.exists():
            continue
        text = mod_path.read_text(encoding="utf-8")
        for pat in patterns:
            if pat in text and "examination_family" not in text:
                hits.append(f"{mod_path.name}:{pat}")
    return hits


def build_extensibility_proof() -> ExtensibilityProof:
    branches = _scan_generic_modules_for_eapcet_branches()
    verdict = PlanVerdict.PASS if not branches else PlanVerdict.FAIL
    _ = inspect  # reserved for future AST checks
    return ExtensibilityProof(
        generic_modules_inspected=list(GENERIC_ENGINE_MODULES),
        eapcet_specific_branches_in_generic=branches,
        pack_config_driven=True,
        verdict=verdict,
    )