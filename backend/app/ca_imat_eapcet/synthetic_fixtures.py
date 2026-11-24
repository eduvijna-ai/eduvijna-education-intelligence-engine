from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.ca_imat_eapcet.constants import (
    CA_PAPER_CODES,
    EAPCET_ENGINEERING_SECTIONS,
    IMAT_OPTIONS_PER_QUESTION,
    IMAT_TOTAL_QUESTIONS,
)
from app.ca_imat_eapcet.contracts import DescriptiveItemContract, DescriptiveSubpart, QuestionRef


def _fp(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


@dataclass(frozen=True, slots=True)
class SyntheticPools:
    objective_by_paper: dict[str, tuple[QuestionRef, ...]]
    descriptive_samples: tuple[DescriptiveItemContract, ...]
    pool_fingerprint: str
    demonstration_only: bool = True


def build_objective_pool(*, paper_code: str, size: int) -> tuple[QuestionRef, ...]:
    items: list[QuestionRef] = []
    for i in range(size):
        qid = f"{paper_code}_syn_{i:03d}"
        items.append(
            QuestionRef(
                question_id=qid,
                paper_or_section=paper_code,
                topic_code="synthetic_topic",
                fingerprint=_fp("ca", paper_code, qid),
                correct_key="A",
                marks_if_correct=1.0,
                marks_if_incorrect=0.0,
                stem_text=f"Original synthetic stem {i} for {paper_code}",
                options={k: f"Option {k}" for k in "ABCD"},
                question_kind="objective",
            )
        )
    return tuple(items)


def build_descriptive_sample(paper_code: str) -> DescriptiveItemContract:
    subparts = [
        DescriptiveSubpart(
            subpart_id=f"{paper_code}_a",
            prompt="Prepare journal entries for the given original scenario.",
            max_marks=4.0,
            model_solution_steps=[
                "Identify accounts",
                "Apply double-entry",
                "Reconcile trial balance",
            ],
            partial_credit_bounds=(0.0, 4.0),
        ),
        DescriptiveSubpart(
            subpart_id=f"{paper_code}_b",
            prompt="Explain the legal principle with reasoned conclusion.",
            max_marks=6.0,
            model_solution_steps=["State provision", "Apply to facts", "Conclude"],
            partial_credit_bounds=(0.0, 6.0),
        ),
    ]
    total = sum(s.max_marks for s in subparts)
    return DescriptiveItemContract(
        item_id=f"{paper_code}_desc_001",
        paper_code=paper_code,
        stem_intro="Original multipart scenario (synthetic, not ICAI copyrighted text).",
        subparts=subparts,
        total_marks=total,
        rubric_valid=True,
        automated_grading_claimed=False,
    )


def build_ca_pools(*, per_paper: int = 25) -> SyntheticPools:
    pools: dict[str, tuple[QuestionRef, ...]] = {}
    for paper in CA_PAPER_CODES:
        if paper.startswith("paper1") or paper.startswith("paper2"):
            continue
        pools[paper] = build_objective_pool(paper_code=paper, size=per_paper)
    descriptive = (
        build_descriptive_sample("paper1_accounting"),
        build_descriptive_sample("paper2_business_laws"),
    )
    fp = _fp("ca_pool", str(len(pools)), str(len(descriptive)))
    return SyntheticPools(
        objective_by_paper=pools,
        descriptive_samples=descriptive,
        pool_fingerprint=fp,
    )


def build_imat_pool() -> tuple[QuestionRef, ...]:
    items: list[QuestionRef] = []
    sections = ("reading", "logic", "biology", "chemistry", "physics", "math")
    per_section = IMAT_TOTAL_QUESTIONS // len(sections)
    idx = 0
    for section in sections:
        for _ in range(per_section):
            qid = f"imat_{section}_{idx:03d}"
            options = {chr(ord("A") + j): f"Choice {j}" for j in range(IMAT_OPTIONS_PER_QUESTION)}
            items.append(
                QuestionRef(
                    question_id=qid,
                    paper_or_section=section,
                    fingerprint=_fp("imat", section, qid),
                    correct_key="A",
                    marks_if_correct=1.5,
                    marks_if_incorrect=0.0,
                    options=options,
                )
            )
            idx += 1
    return tuple(items)


def build_eapcet_pool(*, stream: str) -> tuple[QuestionRef, ...]:
    if stream == "engineering":
        sections = EAPCET_ENGINEERING_SECTIONS
    else:
        from app.ca_imat_eapcet.constants import EAPCET_AP_SECTIONS_REFERENCE

        sections = EAPCET_AP_SECTIONS_REFERENCE
    items: list[QuestionRef] = []
    idx = 0
    for section, count in sections.items():
        for _ in range(count):
            qid = f"eapcet_{stream}_{section}_{idx:04d}"
            items.append(
                QuestionRef(
                    question_id=qid,
                    paper_or_section=section,
                    fingerprint=_fp("eapcet", stream, section, qid),
                    correct_key="B",
                    marks_if_correct=1.0,
                    marks_if_incorrect=0.0,
                    options={k: f"{section} opt {k}" for k in "ABCD"},
                )
            )
            idx += 1
    return tuple(items)