from __future__ import annotations

import hashlib
import json

from app.jee_advanced.contracts import PracticeQuestionRef
from app.jee_advanced.enums import AdvancedIssueCode
from app.jee_advanced.synthetic_fixtures import SyntheticFixturePool, build_synthetic_fixture_pool

SYNTHETIC_ITEMS_PER_PAPER_DEFAULT = 3


def assemble_synthetic_paper_items(
    *,
    paper_codes: list[str],
    pool: SyntheticFixturePool | None = None,
    items_per_paper: int = SYNTHETIC_ITEMS_PER_PAPER_DEFAULT,
    requested_counts: dict[str, int] | None = None,
) -> tuple[dict[str, list[PracticeQuestionRef]], list[AdvancedIssueCode]]:
    """Attach distinct demonstration item IDs per paper (not production-validated Questions)."""

    fixture_pool = pool or build_synthetic_fixture_pool(general_math_count=24, algebra_count=12)
    available = list(fixture_pool.mathematics)
    used_ids: set[str] = set()
    paper_items: dict[str, list[PracticeQuestionRef]] = {}
    issues: list[AdvancedIssueCode] = []

    for paper_code in paper_codes:
        quota = items_per_paper
        if requested_counts and paper_code in requested_counts:
            quota = requested_counts[paper_code]

        chosen: list[PracticeQuestionRef] = []
        for candidate in available:
            if candidate.question_id in used_ids:
                continue
            if not candidate.independently_validated:
                issues.append(AdvancedIssueCode.UNVALIDATED_QUESTION)
                continue
            chosen.append(candidate)
            used_ids.add(candidate.question_id)
            if len(chosen) >= quota:
                break

        if len(chosen) < quota:
            issues.append(AdvancedIssueCode.PAPER_QUOTA_SHORTAGE)
        paper_items[paper_code] = chosen

    ids_per_paper = {code: [q.question_id for q in refs] for code, refs in paper_items.items()}
    if len({qid for ids in ids_per_paper.values() for qid in ids}) != sum(
        len(ids) for ids in ids_per_paper.values()
    ):
        issues.append(AdvancedIssueCode.DUPLICATE_CROSS_PAPER)

    return paper_items, issues


def paper_checksum_from_items(paper_code: str, item_ids: list[str]) -> str:
    payload = {
        "paper": paper_code,
        "item_ids": sorted(item_ids),
        "assembly": "synthetic_assembled",
        "demonstration_only": True,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
