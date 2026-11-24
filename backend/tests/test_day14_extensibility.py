from app.ca_imat_eapcet.enums import PlanVerdict
from app.ca_imat_eapcet.extensibility_proof import build_extensibility_proof


def test_extensibility_no_generic_eapcet_branches() -> None:
    proof = build_extensibility_proof()
    assert proof.pack_config_driven is True
    assert proof.verdict == PlanVerdict.PASS
    assert not proof.eapcet_specific_branches_in_generic