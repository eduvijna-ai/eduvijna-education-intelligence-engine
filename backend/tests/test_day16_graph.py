from app.adaptive_remediation.evidence import normalize_observations
from app.adaptive_remediation.prerequisite_plan import (
    build_prerequisite_targets,
    foundation_first_order,
    graph_ready,
)
from app.adaptive_remediation.synthetic_fixture import (
    ALLOWED_CONCEPT_CODES,
    AUTHORITATIVE_AS_OF,
    AUTHORITATIVE_EVIDENCE_POLICY,
    AUTHORITATIVE_TARGET_CONCEPT,
    INTERNAL_OBSERVATIONS,
)
from app.adaptive_remediation.synthetic_graph import build_friction_remediation_graph
from app.prerequisite_intelligence.audit import build_graph_quality_report


def test_synthetic_graph_passes_audit() -> None:
    graph = build_friction_remediation_graph()
    ok, _, _ = graph_ready(graph)
    report = build_graph_quality_report(graph)
    assert ok is True
    assert report.status.value in {"pass", "PASS"}


def test_foundation_first_order_complete_or_empty() -> None:
    graph = build_friction_remediation_graph()
    target = next(n for n in graph.nodes if n.concept_code == AUTHORITATIVE_TARGET_CONCEPT)
    result = foundation_first_order(graph, target.concept_id, budget=6)
    assert result.complete
    assert "newton-laws" in result.order


def test_foundation_order_rejects_cycle_extension() -> None:
    graph = build_friction_remediation_graph()
    formula = next(n for n in graph.nodes if n.concept_code == "friction-formula-selection")
    newton = next(n for n in graph.nodes if n.concept_code == "newton-laws")
    from app.prerequisite_intelligence.contracts import PrerequisiteGraphEdge
    from app.prerequisite_intelligence.enums import EdgeProvenanceClass

    cyclic = graph.model_copy(
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
    result = foundation_first_order(cyclic, formula.concept_id, budget=8)
    assert not result.complete


def test_prerequisite_targets_include_hypothesis_without_observation() -> None:
    graph = build_friction_remediation_graph()
    bundle = normalize_observations(
        INTERNAL_OBSERVATIONS,
        curriculum_version_code="d16-synth-physics-v1",
        allowed_concept_codes=ALLOWED_CONCEPT_CODES,
        as_of=AUTHORITATIVE_AS_OF,
        evidence_policy_version=AUTHORITATIVE_EVIDENCE_POLICY,
    )
    targets = build_prerequisite_targets(graph, bundle, AUTHORITATIVE_TARGET_CONCEPT)
    codes = {t.concept_code for t in targets}
    assert "newton-laws" in codes
    newton = next(t for t in targets if t.concept_code == "newton-laws")
    assert "hypothesis" in newton.rationale.lower()
