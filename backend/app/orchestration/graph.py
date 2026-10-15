from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.nodes.author import author_node
from app.orchestration.nodes.duplicate_validate import duplicate_validate_node
from app.orchestration.nodes.human_gate import human_gate_node
from app.orchestration.nodes.plan import plan_generation_node
from app.orchestration.nodes.repair import repair_planner_node
from app.orchestration.nodes.resolve_context import resolve_context_node
from app.orchestration.nodes.resolve_scope import resolve_scope_node
from app.orchestration.nodes.reviewers import reviewers_node
from app.orchestration.nodes.solver import solver_node
from app.orchestration.nodes.validate import deterministic_validate_node
from app.orchestration.nodes.whole_output import whole_output_node
from app.orchestration.routing import (
    route_after_fallible,
    route_after_human,
    route_after_scope,
    route_after_validation,
)
from app.orchestration.state import OrchestrationGraphState


def _bind(
    fn: Callable[..., dict[str, Any]],
    deps: OrchestrationDependencies,
) -> Callable[[OrchestrationGraphState], dict[str, Any]]:
    def node(state: OrchestrationGraphState) -> dict[str, Any]:
        return fn(state, deps)

    return node


def _continue_or_output(state: OrchestrationGraphState) -> str:
    return "whole_output" if route_after_fallible(state) == "whole_output" else "continue"


def build_orchestration_graph(
    deps: OrchestrationDependencies, *, checkpointer: object | None = None
) -> object:
    graph = StateGraph(OrchestrationGraphState)
    graph.add_node("resolve_scope", _bind(resolve_scope_node, deps))  # type: ignore[call-overload]
    graph.add_node("resolve_context", _bind(resolve_context_node, deps))  # type: ignore[call-overload]
    graph.add_node("plan_generation", _bind(plan_generation_node, deps))  # type: ignore[call-overload]
    graph.add_node("author", _bind(author_node, deps))  # type: ignore[call-overload]
    graph.add_node("solver", _bind(solver_node, deps))  # type: ignore[call-overload]
    graph.add_node("reviewers", _bind(reviewers_node, deps))  # type: ignore[call-overload]
    graph.add_node("deterministic_validate", _bind(deterministic_validate_node, deps))  # type: ignore[call-overload]
    graph.add_node("duplicate_validate", _bind(duplicate_validate_node, deps))  # type: ignore[call-overload]
    graph.add_node("repair", _bind(repair_planner_node, deps))  # type: ignore[call-overload]
    graph.add_node("human_gate", _bind(human_gate_node, deps))  # type: ignore[call-overload]
    graph.add_node("whole_output", _bind(whole_output_node, deps))  # type: ignore[call-overload]

    graph.add_edge(START, "resolve_scope")
    graph.add_conditional_edges(
        "resolve_scope",
        route_after_scope,
        {"resolve_context": "resolve_context", "whole_output": "whole_output"},
    )
    graph.add_conditional_edges(
        "resolve_context",
        _continue_or_output,
        {"continue": "plan_generation", "whole_output": "whole_output"},
    )
    graph.add_conditional_edges(
        "plan_generation",
        _continue_or_output,
        {"continue": "author", "whole_output": "whole_output"},
    )
    graph.add_conditional_edges(
        "author",
        _continue_or_output,
        {"continue": "solver", "whole_output": "whole_output"},
    )
    graph.add_conditional_edges(
        "solver",
        _continue_or_output,
        {"continue": "reviewers", "whole_output": "whole_output"},
    )
    graph.add_conditional_edges(
        "reviewers",
        _continue_or_output,
        {"continue": "deterministic_validate", "whole_output": "whole_output"},
    )
    graph.add_edge("deterministic_validate", "duplicate_validate")
    graph.add_conditional_edges(
        "duplicate_validate",
        route_after_validation,
        {
            "repair": "repair",
            "human_gate": "human_gate",
            "whole_output": "whole_output",
        },
    )
    graph.add_edge("repair", "author")
    graph.add_conditional_edges(
        "human_gate",
        route_after_human,
        {"deterministic_validate": "deterministic_validate", "whole_output": "whole_output"},
    )
    graph.add_edge("whole_output", END)

    return graph.compile(checkpointer=checkpointer)  # type: ignore[arg-type]
