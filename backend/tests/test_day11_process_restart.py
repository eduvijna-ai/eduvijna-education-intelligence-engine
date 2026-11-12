from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.common.trust_execution import TrustExecutionMode
from app.core.config import Settings
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.jee_main_exam_intelligence.contracts import PaperPlanRequest
from app.jee_main_exam_intelligence.enums import (
    JeeMainSubjectCode,
    PaperPlanIssueCode,
    PaperPlanMode,
    PaperPlanVerdict,
)
from app.jee_main_exam_intelligence.fixtures import (
    build_practice_math_ten_request,
    seed_day11_fixture_context,
)
from app.jee_main_exam_intelligence.orchestration_bridge import (
    _production_trust_envelope_allowed,
    trust_envelope_from_orchestration_result,
)
from app.jee_main_exam_intelligence.service import JeeMainExamIntelligenceService
from app.models.orchestration import (
    OrchestrationAuditEvent,
    OrchestrationGenerationCall,
    OrchestrationIdempotencyRecord,
)
from app.models.question import TestDefinition, TestQuestion
from app.orchestration.checkpoint import build_managed_checkpointer
from app.orchestration.contracts import OrchestrationRequest
from app.orchestration.control_session import open_control_session
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.factory import build_orchestration_service
from app.orchestration.fixtures import build_orchestration_request, seed_day8_fixtures
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.human_decision import HumanResumeDecision


def _row_count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _worker(db_path: Path, state_path: Path, phase: str) -> None:
    """Run in an independent Python interpreter, never a reused session."""
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    settings = Settings(database_url=url)
    gateway = FakeGenerationGateway()
    adapter = FakeAnythingLLMAdapter()

    with Session(engine) as session:
        if phase == "pause":
            ctx = seed_day8_fixtures(session, adapter=adapter)
            request = build_orchestration_request(
                ctx,
                scenario="human_review",
                idempotency_key="d11-process-restart-001",
            )
        else:
            previous = json.loads(state_path.read_text(encoding="utf-8"))
            request = OrchestrationRequest.model_validate(previous["request"])

        managed = build_managed_checkpointer(settings, memory_only=False)
        service = build_orchestration_service(
            session,
            gateway=gateway,
            knowledge_adapter=adapter,
            checkpointer=managed,
            force_fake=True,
        )
        try:
            if phase == "pause":
                result = service.run(request)
                assert result.status == OrchestrationRunStatus.REVIEW_REQUIRED
                # SQLite uses its dedicated Day8 *.orchestration.sqlite
                # control DB for durable audit/idempotency, not the app DB.
                with open_control_session(session) as control:
                    generation_calls = _row_count(control, OrchestrationGenerationCall)
                    audit_count = _row_count(control, OrchestrationAuditEvent)
                assert len(gateway.call_history()) > 0
                state_path.write_text(
                    json.dumps(
                        {
                            "request": request.model_dump(mode="json"),
                            "run_id": result.run_id,
                            "generation_calls": generation_calls,
                            "audit_count": audit_count,
                        },
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
            elif phase == "resume":
                result = service.run(
                    request, resume=HumanResumeDecision(action="approve")
                )
                assert result.status == OrchestrationRunStatus.COMPLETED
                assert result.run_id == previous["run_id"]
                assert len(gateway.call_history()) == 0
                with open_control_session(session) as control:
                    assert _row_count(control, OrchestrationGenerationCall) == previous[
                        "generation_calls"
                    ]
                    audit_before = _row_count(control, OrchestrationAuditEvent)
                completed = service.run(request)
                assert completed.status == OrchestrationRunStatus.COMPLETED
                assert completed.run_id == result.run_id
                assert completed.model_dump(mode="json") == result.model_dump(mode="json")
                with open_control_session(session) as control:
                    assert _row_count(control, OrchestrationAuditEvent) == audit_before
                    idempotency_rows = control.scalars(
                        select(OrchestrationIdempotencyRecord).where(
                            OrchestrationIdempotencyRecord.idempotency_key
                            == request.idempotency_key
                        )
                    ).all()
                assert len(gateway.call_history()) == 0
                assert len(idempotency_rows) == 1
                assert idempotency_rows[0].status == "completed"
                assert result.items
                item = result.items[0]
                envelope = trust_envelope_from_orchestration_result(result)[item.item_id]
                paper = PaperPlanRequest(
                    plan_id="process-restart-check",
                    exam_version_code="2027",
                    mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
                    organization_id=request.organization_id,
                    institution_id=request.institution_id,
                    subject_code=JeeMainSubjectCode.MATHEMATICS,
                    requested_count=1,
                    execution_mode=TrustExecutionMode.PRODUCTION,
                )
                assert _production_trust_envelope_allowed(session, paper, item, envelope)
                forged = {**envelope, "orchestration_run_id": "unknown-run"}
                assert not _production_trust_envelope_allowed(session, paper, item, forged)
            else:
                raise AssertionError(f"unknown worker phase: {phase}")
        finally:
            service.close()
            session.commit()
    engine.dispose()


def test_day11_human_review_survives_independent_worker_process_restart() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        database = root / "day11-worker.db"
        state = root / "checkpoint-result.json"
        for phase in ("pause", "resume"):
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), str(database), str(state), phase],
                check=False,
                capture_output=True,
                text=True,
                timeout=80,
            )
            assert completed.returncode == 0, (
                f"Day11 {phase} process failed:\n"
                f"stdout={completed.stdout[-2500:]}\n"
                f"stderr={completed.stderr[-5000:]}"
            )
        assert state.exists()
        assert Path(str(database) + ".langgraph.sqlite").exists()



def _paper_worker(db_path: Path, state_path: Path, phase: str) -> None:
    """Verify persisted paper identity and idempotency across fresh processes."""
    engine = create_engine(f"sqlite:///{db_path}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        service = JeeMainExamIntelligenceService()
        if phase == "paper-create":
            ctx = seed_day11_fixture_context(session)
            session.commit()
            request = build_practice_math_ten_request(ctx).model_copy(
                update={
                    "plan_id": "day11-process-paper",
                    "idempotency_key": "day11-process-paper-01",
                }
            )
            result = service.plan_paper(session, request)
            assert result.verdict == PaperPlanVerdict.PASS
            assert result.actual_count == 10
            session.commit()
            assert result.test_definition_id is not None
            assert _row_count(session, TestDefinition) == 1
            assert _row_count(session, TestQuestion) == 10
            state_path.write_text(
                json.dumps(
                    {
                        "request": request.model_dump(mode="json"),
                        "test_definition_id": result.test_definition_id,
                        "plan_checksum": result.plan_checksum,
                        "question_ids": [s.question_id for s in result.slots],
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
        elif phase == "paper-replay":
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            request = PaperPlanRequest.model_validate(saved["request"])
            before_definitions = _row_count(session, TestDefinition)
            before_items = _row_count(session, TestQuestion)
            result = service.plan_paper(session, request)
            assert result.verdict == PaperPlanVerdict.PASS
            assert result.test_definition_id == saved["test_definition_id"]
            assert result.plan_checksum == saved["plan_checksum"]
            assert [s.question_id for s in result.slots] == saved["question_ids"]
            assert _row_count(session, TestDefinition) == before_definitions
            assert _row_count(session, TestQuestion) == before_items
            conflict_request = request.model_copy(update={"derived_topic_group": "algebra"})
            conflict = service.plan_paper(session, conflict_request)
            assert conflict.verdict == PaperPlanVerdict.FAIL
            assert PaperPlanIssueCode.REPLAY_IDEMPOTENCY_CONFLICT in conflict.issue_codes
            session.commit()
            assert _row_count(session, TestDefinition) == before_definitions
            assert _row_count(session, TestQuestion) == before_items
        else:
            raise AssertionError(f"unknown paper phase: {phase}")
    engine.dispose()


def test_day11_persisted_paper_replay_is_stable_across_worker_processes() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        database = root / "day11-paper.db"
        state = root / "saved-paper.json"
        for phase in ("paper-create", "paper-replay"):
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), str(database), str(state), phase],
                check=False,
                capture_output=True,
                text=True,
                timeout=80,
            )
            assert completed.returncode == 0, (
                f"Day11 {phase} process failed:\n"
                f"stdout={completed.stdout[-2500:]}\n"
                f"stderr={completed.stderr[-5000:]}"
            )



if __name__ == "__main__":
    if sys.argv[3].startswith("paper-"):
        _paper_worker(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
    else:
        _worker(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
