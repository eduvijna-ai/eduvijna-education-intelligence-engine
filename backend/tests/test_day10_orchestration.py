from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.orchestration.contracts import DraftQuestionItem, OrchestrationRequest, QuestionOptionDraft
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.fixtures import build_day8_test_service
from app.orchestration.nodes.whole_output import whole_output_node


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _draft(item_id: str = "item-1") -> dict:
    return DraftQuestionItem(
        item_id=item_id,
        slot_index=0,
        stem_text="2 + 2 = ?",
        options=[
            QuestionOptionDraft(option_key="A", text="3", is_correct=False),
            QuestionOptionDraft(option_key="B", text="4", is_correct=True),
        ],
    ).model_dump(mode="json")


def _request(**metadata) -> OrchestrationRequest:
    return OrchestrationRequest(
        idempotency_key="rc-whole-output-key",
        retrieval_profile_version="v1",
        requested_count=1,
        metadata_json=metadata,
    )


def _run_whole_output(state: dict) -> OrchestrationRunStatus:
    session = _session()
    _, service = build_day8_test_service(session)
    update = whole_output_node(state, service.dependencies)
    result = update["final_result"]
    session.close()
    return OrchestrationRunStatus(result["status"])


def test_whole_output_root_cause_success_completes() -> None:
    request = _request(root_cause_enrichment_enabled=True)
    state = {
        "run_id": "run-rc-ok",
        "request": request.model_dump(mode="json"),
        "request_hash": request.request_hash(),
        "resolved_scope": {},
        "draft_items": [_draft()],
        "root_cause_eligible_tag_count": 1,
        "root_cause_results": [
            {
                "item_id": "item-1",
                "option_key": "A",
                "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                "verdict_status": "pass",
            }
        ],
        "node_attempts": {},
    }
    assert _run_whole_output(state) == OrchestrationRunStatus.COMPLETED


def test_whole_output_root_cause_not_applicable_completes() -> None:
    request = _request(root_cause_enrichment_enabled=True)
    state = {
        "run_id": "run-rc-na",
        "request": request.model_dump(mode="json"),
        "request_hash": request.request_hash(),
        "resolved_scope": {},
        "draft_items": [_draft()],
        "root_cause_eligible_tag_count": 0,
        "root_cause_results": [],
        "node_attempts": {},
    }
    assert _run_whole_output(state) == OrchestrationRunStatus.COMPLETED


def test_whole_output_root_cause_incomplete_review() -> None:
    request = _request(root_cause_enrichment_enabled=True)
    state = {
        "run_id": "run-rc-inc",
        "request": request.model_dump(mode="json"),
        "request_hash": request.request_hash(),
        "resolved_scope": {},
        "draft_items": [_draft()],
        "root_cause_eligible_tag_count": 2,
        "root_cause_results": [
            {
                "item_id": "item-1",
                "option_key": "A",
                "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                "verdict_status": "pass",
            }
        ],
        "node_attempts": {},
    }
    assert _run_whole_output(state) == OrchestrationRunStatus.REVIEW_REQUIRED


def test_whole_output_root_cause_non_pass_review() -> None:
    request = _request(root_cause_enrichment_enabled=True)
    state = {
        "run_id": "run-rc-fail",
        "request": request.model_dump(mode="json"),
        "request_hash": request.request_hash(),
        "resolved_scope": {},
        "draft_items": [_draft()],
        "root_cause_eligible_tag_count": 1,
        "root_cause_results": [
            {
                "item_id": "item-1",
                "option_key": "A",
                "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                "verdict_status": "review_required",
            }
        ],
        "node_attempts": {},
    }
    assert _run_whole_output(state) == OrchestrationRunStatus.REVIEW_REQUIRED


def test_whole_output_root_cause_disabled_baseline() -> None:
    request = _request(root_cause_enrichment_enabled=False)
    state = {
        "run_id": "run-rc-off",
        "request": request.model_dump(mode="json"),
        "request_hash": request.request_hash(),
        "resolved_scope": {},
        "draft_items": [_draft()],
        "node_attempts": {},
    }
    assert _run_whole_output(state) == OrchestrationRunStatus.COMPLETED
