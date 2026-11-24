from app.adaptive_remediation.contracts import TeacherPolicyOverride
from app.adaptive_remediation.fingerprint import plan_fingerprint
from app.adaptive_remediation.service import AdaptiveRemediationDiagnosticService
from app.adaptive_remediation.synthetic_graph import build_friction_remediation_graph
from app.adaptive_remediation.teacher_policy import apply_teacher_policy
from app.prerequisite_intelligence.audit import build_graph_quality_report
from app.prerequisite_intelligence.contracts import PrerequisiteGraphEdge
from app.prerequisite_intelligence.enums import EdgeProvenanceClass


def test_fingerprint_stable_on_replay() -> None:
    service = AdaptiveRemediationDiagnosticService()
    req = service.build_authoritative_demo_request()
    fp1 = plan_fingerprint(req, policy_version="d16-adaptive-policy-v1")
    fp2 = plan_fingerprint(req, policy_version="d16-adaptive-policy-v1")
    assert fp1 == fp2


def test_teacher_override_cannot_exceed_academic_max() -> None:
    override = TeacherPolicyOverride(
        override_id="t1",
        allowed_max_count=5,
        provenance="synthetic",
        precedence_rank=1,
    )
    assert apply_teacher_policy(override, academic_max_count=10) == 5


def test_cycle_in_graph_fails_audit() -> None:
    graph = build_friction_remediation_graph()
    formula = next(n for n in graph.nodes if n.concept_code == "friction-formula-selection")
    newton = next(n for n in graph.nodes if n.concept_code == "newton-laws")
    bad = graph.model_copy(
        update={
            "edges": [
                *graph.edges,
                PrerequisiteGraphEdge(
                    edge_id="d16-cycle",
                    prerequisite_concept_id=formula.concept_id,
                    target_concept_id=newton.concept_id,
                    provenance_class=EdgeProvenanceClass.SYNTHETIC,
                ),
            ]
        }
    )
    report = build_graph_quality_report(bad)
    assert report.status.value in {"fail", "FAIL"}
