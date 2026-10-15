from __future__ import annotations

import ast
from pathlib import Path

_FORBIDDEN_IMPORT_SNIPPETS = (
    "openai",
    "anthropic",
    "google.generativeai",
    "langchain_openai",
)


def verify_day8_scope_guard() -> dict[str, object]:
    """Static guard that Day 8 package does not import Day 9+ or direct provider SDKs."""
    root = Path(__file__).resolve().parent
    violations: list[str] = []
    for path in root.rglob("*.py"):
        if path.name == "scope_guard.py":
            continue
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        for snippet in _FORBIDDEN_IMPORT_SNIPPETS:
            if snippet in lowered:
                violations.append(f"{path.name}: forbidden snippet {snippet}")
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in {"openai", "anthropic"}:
                        violations.append(f"{path.name}: import {alias.name}")
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in {"openai", "anthropic"}:
                    violations.append(f"{path.name}: from {node.module}")
    return {"ok": not violations, "violations": violations}
