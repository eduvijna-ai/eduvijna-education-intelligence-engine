from app.ca_imat_eapcet.enums import PlanVerdict
from app.ca_imat_eapcet.extensibility_proof import (
    build_extensibility_proof,
    exercise_config_driven_onboarding,
)


def test_extensibility_config_demo_without_generic_branch() -> None:
    proof = build_extensibility_proof()
    assert proof.pack_config_driven is False
    assert proof.verdict in {PlanVerdict.REVIEW_REQUIRED, PlanVerdict.NOT_READY}
    assert not proof.eapcet_specific_branches_in_generic


def test_onboarding_exercise_delivers() -> None:
    assert exercise_config_driven_onboarding() == PlanVerdict.PASS