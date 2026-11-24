from app.adaptive_remediation.contracts import TeacherPolicyOverride
from app.adaptive_remediation.internal_demo import build_authoritative_synthetic_plan
from app.adaptive_remediation.service import AdaptiveRemediationDiagnosticService
from app.adaptive_remediation.synthetic_graph import build_friction_remediation_graph
from app.adaptive_remediation.teacher_policy import TeacherPolicyApplication, apply_teacher_policy
from app.prerequisite_intelligence.audit import build_graph_quality_report
from app.prerequisite_intelligence.contracts import PrerequisiteGraphEdge
from app.prerequisite_intelligence.enums import EdgeProvenanceClass


def test_plan_replay_deterministic() -> None:
    a = build_authoritative_synthetic_plan()
    b = build_authoritative_synthetic_plan()
    assert a.fingerprint == b.fingerprint
    assert a.stages == b.stages
    assert a.targets == b.targets


def test_teacher_override_count_conflict() -> None:
    override = TeacherPolicyOverride(
        override_id="t1",
        allowed_max_count=5,
        provenance="synthetic-contract-only",
        precedence_rank=1,
    )
    result = apply_teacher_policy(override, academic_max_count=10, requested_count=10)
    assert isinstance(result, TeacherPolicyApplication)
    assert result.accepted is False
    assert result.reason == "OVERRIDE_COUNT_CONFLICT"


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


def test_runtime_service_matches_boundary() -> None:
    service = AdaptiveRemediationDiagnosticService()
    blocked = service.attempt_runtime_remediation(fake_request=object())
    assert blocked.requested_count == 0
