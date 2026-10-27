from __future__ import annotations

import ast
from pathlib import Path

_FORBIDDEN_IMPORT_PREFIXES = (
    "openai",
    "anthropic",
    "google.generativeai",
    "langchain_openai",
)

_FORBIDDEN_SCOPE_TOKENS = (
    "jee_main_blueprint",
    "learner_mastery_store",
    "remediation_plan_engine",
)


def verify_day10_scope_guard() -> dict[str, object]:
    roots = [
        Path(__file__).resolve().parent,
        Path(__file__).resolve().parents[1] / "root_cause_intelligence",
        Path(__file__).resolve().parents[1] / "paper_distribution",
    ]
    violations: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in _FORBIDDEN_SCOPE_TOKENS:
                if token in text:
                    violations.append(f"{path.name}: forbidden token {token}")
            try:
                tree = ast.parse(text, filename=str(path))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if any(
                            alias.name == prefix or alias.name.startswith(f"{prefix}.")
                            for prefix in _FORBIDDEN_IMPORT_PREFIXES
                        ):
                            violations.append(f"{path.name}: import {alias.name}")
                if isinstance(node, ast.ImportFrom) and node.module:
                    if any(
                        node.module == prefix or node.module.startswith(f"{prefix}.")
                        for prefix in _FORBIDDEN_IMPORT_PREFIXES
                    ):
                        violations.append(f"{path.name}: from {node.module}")
    return {"ok": not violations, "violations": violations}
