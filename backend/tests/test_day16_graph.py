from app.adaptive_remediation.prerequisite_plan import foundation_first_order, graph_ready
from app.adaptive_remediation.synthetic_graph import build_friction_remediation_graph
from app.prerequisite_intelligence.audit import build_graph_quality_report


def test_synthetic_graph_passes_audit() -> None:
    graph = build_friction_remediation_graph()
    ok, verdict, _ = graph_ready(graph)
    report = build_graph_quality_report(graph)
    assert ok is True
    assert verdict.value == "DIAGNOSTIC_PLAN"
    assert report.status.value in {"pass", "PASS"}


def test_foundation_first_order_bounded() -> None:
    graph = build_friction_remediation_graph()
    target = next(n for n in graph.nodes if n.concept_code == "friction-formula-selection")
    order = foundation_first_order(graph, target.concept_id, budget=3)
    assert "newton-laws" in order
    assert len(order) <= 3
