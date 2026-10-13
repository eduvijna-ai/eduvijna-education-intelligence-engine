"""Day 7 scope guard tests (D7-01 / D7-36 subset)."""

from __future__ import annotations

from pathlib import Path

from app.repo_paths import RepositoryRootError, execution_spec_file


def _day7_spec_path() -> Path:
    try:
        return execution_spec_file("docs/execution/D07-KNOWLEDGE-INTELLIGENCE-ANYTHINGLLM.md")
    except RepositoryRootError:
        return (
            Path(__file__).resolve().parent
            / "fixtures"
            / "D07-KNOWLEDGE-INTELLIGENCE-ANYTHINGLLM.scope-guard.md"
        )


def test_day7_docs_exclude_langgraph_public_api_and_question_generation() -> None:
    spec = _day7_spec_path()
    text = spec.read_text(encoding="utf-8").lower()
    assert "langgraph orchestration is day 8" in text
    assert "question generation is not part of day 7" in text
    assert "public rest/mcp product endpoints are day 17" in text


def test_knowledge_package_has_no_langgraph_imports() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app/knowledge_intelligence"
    joined = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "langgraph" not in joined.lower()
