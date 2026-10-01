from app.adapters.anythingllm.provider import AnythingLLMProvider
from app.agents.types import AgentExecutionResult, AgentState
from app.core.context import TenantContext


def test_day1_boundaries_construct() -> None:
    provider = AnythingLLMProvider(None, None)
    assert provider.configured is False
    assert TenantContext().organization_id == "local-org"
    state = AgentState(run_id="run-1")
    result = AgentExecutionResult(run_id="run-1", status="ok")
    assert state.run_id == result.run_id
