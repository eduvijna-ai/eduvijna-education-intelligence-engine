from __future__ import annotations

import ast
from pathlib import Path

_FORBIDDEN_IMPORT_PREFIXES = (
    "openai",
    "anthropic",
    "google.generativeai",
    "langchain_openai",
)

_FORBIDDEN_DAY10_TOKENS = (
    "prerequisite_graph",
    "root_cause_engine",
    "learner_mastery",
    "remediation_plan",
)


def _forbidden_import(module_name: str) -> bool:
    return any(
        module_name == prefix or module_name.startswith(f"{prefix}.")
        for prefix in _FORBIDDEN_IMPORT_PREFIXES
    )


def verify_day9_scope_guard() -> dict[str, object]:
    root = Path(__file__).resolve().parent
    violations: list[str] = []
    for path in root.rglob("*.py"):
        if path.name == "scope_guard.py":
            continue
        text = path.read_text(encoding="utf-8")
        for token in _FORBIDDEN_DAY10_TOKENS:
            if token in text:
                violations.append(f"{path.name}: forbidden token {token}")
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _forbidden_import(alias.name):
                        violations.append(f"{path.name}: import {alias.name}")
            if isinstance(node, ast.ImportFrom) and node.module:
                if _forbidden_import(node.module):
                    violations.append(f"{path.name}: from {node.module}")
    return {"ok": not violations, "violations": violations}
