from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.trust_execution import TrustExecutionMode
from app.jee_main_exam_intelligence.contracts import PaperPlanRequest, PaperPlanSlot
from app.jee_main_exam_intelligence.enums import PaperPlanIssueCode, PaperPlanVerdict
from app.jee_main_exam_intelligence.trusted_validation import synthetic_trust_permitted
from app.models.question import Question
from app.paper_distribution.contracts import (
    DistributionTarget,
    PaperDistributionRequest,
    PaperItemInput,
)
from app.paper_distribution.enums import PaperDistributionVerdict
from app.paper_distribution.evaluator import evaluate_paper_distribution_with_session
from app.paper_distribution.trusted_validation import (
    PaperDay6ItemBinding,
    PaperDay6TrustContext,
)


def evaluate_plan_paper_distribution(
    session: Session,
    *,
    request: PaperPlanRequest,
    slots: list[PaperPlanSlot],
    execution_mode: TrustExecutionMode,
) -> tuple[PaperPlanVerdict, list[PaperPlanIssueCode], dict[str, object]]:
    """D11-25: Day10 cognitive/competency evaluator on assembled plan items."""
    issues: list[PaperPlanIssueCode] = []
    meta = request.metadata_json or {}
    if not meta.get("evaluate_paper_distribution"):
        return PaperPlanVerdict.PASS, issues, {}

    targets_cfg = meta.get("cognitive_targets") or []
    competency_targets_cfg = meta.get("competency_targets") or []
    if not targets_cfg and not competency_targets_cfg:
        return PaperPlanVerdict.PASS, issues, {"skipped": "no_targets_configured"}
    competency_targets = meta.get("competency_targets") or []
    cognitive_targets = [
        DistributionTarget.model_validate(entry) for entry in targets_cfg
    ]
    competency_models = [
        DistributionTarget.model_validate(entry) for entry in competency_targets
    ]

    item_ids = [s.question_id for s in slots if s.question_id]
    questions = {
        q.id: q
        for q in session.scalars(select(Question).where(Question.id.in_(item_ids)))
    }
    items: list[PaperItemInput] = []
    for slot in slots:
        if not slot.question_id:
            continue
        question = questions.get(slot.question_id)
        if question is None:
            continue
        qmeta = question.metadata_json or {}
        item_id = question.external_code or question.id
        is_synthetic = synthetic_trust_permitted(execution_mode)
        items.append(
            PaperItemInput(
                item_id=item_id,
                marks=slot.marks if slot.marks is not None else qmeta.get("marks"),
                cognitive_level=qmeta.get("declared_cognitive_level")
                or qmeta.get("cognitive_level"),
                competency_codes=list(qmeta.get("competency_codes") or []),
                primary_competency_code=qmeta.get("primary_competency_code"),
                day6_validated=is_synthetic
                or bool(qmeta.get("day6_validation_run_id")),
                metadata_json=qmeta,
            )
        )

    dist_request = PaperDistributionRequest(
        paper_id=request.plan_id,
        requested_count=request.requested_count,
        items=items,
        cognitive_targets=cognitive_targets,
        competency_targets=competency_models,
        include_mark_weighted=bool(meta.get("include_mark_weighted", True)),
    )
    if synthetic_trust_permitted(execution_mode):
        day6_trust: PaperDay6TrustContext | None = (
            PaperDay6TrustContext.synthetic_fixture_harness()
        )
    else:
        bindings = [
            PaperDay6ItemBinding(
                item_id=item.item_id,
                validation_run_id=str((item.metadata_json or {})["day6_validation_run_id"]),
            )
            for item in items
            if (item.metadata_json or {}).get("day6_validation_run_id")
        ]
        day6_trust = PaperDay6TrustContext.from_item_bindings(bindings)

    result = evaluate_paper_distribution_with_session(
        session,
        dist_request,
        day6_trust=day6_trust,
        execution_mode=execution_mode,
    )
    summary: dict[str, object] = {
        "verdict": result.verdict.value,
        "item_count": result.item_count,
        "issue_codes": [code.value for code in result.issue_codes],
        "cognitive_summary": result.cognitive_summary.model_dump(mode="json"),
        "competency_summary": result.competency_summary.model_dump(mode="json"),
    }
    if result.verdict != PaperDistributionVerdict.PASS:
        issues.append(PaperPlanIssueCode.COGNITIVE_DISTRIBUTION_VIOLATION)
        return PaperPlanVerdict.FAIL, issues, summary
    return PaperPlanVerdict.PASS, issues, summary
