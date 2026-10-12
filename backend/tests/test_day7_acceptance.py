"""Day 7 scope guard tests (D7-01 / D7-36 subset)."""

from __future__ import annotations

from pathlib import Path


def test_day7_docs_exclude_langgraph_public_api_and_question_generation() -> None:
    spec = (
        Path(__file__).resolve().parents[2]
        / "docs/execution/D07-KNOWLEDGE-INTELLIGENCE-ANYTHINGLLM.md"
    )
    text = spec.read_text(encoding="utf-8").lower()
    assert "langgraph orchestration is day 8" in text
    assert "question generation is not part of day 7" in text
    assert "public rest/mcp product endpoints are day 17" in text


def test_knowledge_package_has_no_langgraph_imports() -> None:
    root = Path(__file__).resolve().parents[1] / "app/knowledge_intelligence"
    joined = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "langgraph" not in joined.lower()
