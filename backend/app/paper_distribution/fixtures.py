from __future__ import annotations

from app.paper_distribution.contracts import (
    DistributionTarget,
    PaperDistributionRequest,
    PaperItemInput,
)
from app.paper_distribution.enums import MultiLabelPolicy


def build_demo_ten_question_paper() -> PaperDistributionRequest:
    """2/2/4/1/1 cognitive mix → 20/20/40/10/10 on ten items."""
    cognitive_mix = (
        ["remember"] * 2
        + ["understand"] * 2
        + ["apply"] * 4
        + ["analyze"] * 1
        + ["evaluate"] * 1
    )
    items: list[PaperItemInput] = []
    competencies = [
        "knowledge",
        "conceptual_understanding",
        "application",
        "analysis",
        "problem_solving",
        "hots",
    ]
    for index, cognitive in enumerate(cognitive_mix, start=1):
        comp = competencies[index % len(competencies)]
        items.append(
            PaperItemInput(
                item_id=f"demo-q-{index:02d}",
                marks=1.0,
                cognitive_level=cognitive,
                competency_codes=[comp],
                primary_competency_code=comp,
                day6_validated=True,
            )
        )
    return PaperDistributionRequest(
        paper_id="d10-demo-paper-10",
        requested_count=10,
        items=items,
        cognitive_targets=[
            DistributionTarget(dimension="cognitive", key="remember", exact_percent=20.0),
            DistributionTarget(dimension="cognitive", key="understand", exact_percent=20.0),
            DistributionTarget(dimension="cognitive", key="apply", exact_percent=40.0),
            DistributionTarget(dimension="cognitive", key="analyze", exact_percent=10.0),
            DistributionTarget(dimension="cognitive", key="evaluate", exact_percent=10.0),
        ],
        multi_label_policy=MultiLabelPolicy.PRIMARY_ONLY,
    )


def build_mismatched_target_paper(base: PaperDistributionRequest) -> PaperDistributionRequest:
    return base.model_copy(
        update={
            "paper_id": "d10-demo-paper-mismatch",
            "cognitive_targets": [
                DistributionTarget(dimension="cognitive", key="remember", exact_percent=50.0),
                DistributionTarget(dimension="cognitive", key="understand", exact_percent=50.0),
            ],
        }
    )
