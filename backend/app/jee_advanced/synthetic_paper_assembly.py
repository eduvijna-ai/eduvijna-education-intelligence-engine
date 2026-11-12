from __future__ import annotations

import hashlib
import json
from typing import Any

from app.jee_advanced.constants import (
    OFFICIAL_SUBJECTS,
    PAPER_1_CODE,
    PAPER_2_CODE,
    SYNTHETIC_DEFAULT_ITEMS_PER_PAPER,
    SYNTHETIC_MAX_ITEMS_PER_PAPER,
    SYNTHETIC_SUBJECT_QUOTA_PER_PAPER,
)
from app.jee_advanced.contracts import PracticeQuestionRef
from app.jee_advanced.enums import AdvancedIssueCode
from app.jee_advanced.synthetic_fixtures import SyntheticFixturePool, build_synthetic_fixture_pool

_SUPPORTED_PAPER_KEYS = frozenset({PAPER_1_CODE, PAPER_2_CODE})


def validate_requested_counts(
    requested_counts: dict[str, Any] | None,
    *,
    paper_codes: list[str],
) -> list[AdvancedIssueCode]:
    if not requested_counts:
        return []

    issues: list[AdvancedIssueCode] = []
    for key, value in requested_counts.items():
        if key not in _SUPPORTED_PAPER_KEYS:
            issues.append(AdvancedIssueCode.INVALID_REQUESTED_COUNT)
            continue
        if key not in paper_codes:
            issues.append(AdvancedIssueCode.INVALID_REQUESTED_COUNT)
            continue
        if not isinstance(value, int) or isinstance(value, bool):
            issues.append(AdvancedIssueCode.INVALID_REQUESTED_COUNT)
            continue
        if value <= 0 or value > SYNTHETIC_MAX_ITEMS_PER_PAPER:
            issues.append(AdvancedIssueCode.INVALID_REQUESTED_COUNT)
    return issues


def _expected_subject_total() -> int:
    return sum(SYNTHETIC_SUBJECT_QUOTA_PER_PAPER.values())


def _select_for_paper(
    *,
    pool: SyntheticFixturePool,
    quota: int,
    used_ids: set[str],
) -> tuple[list[PracticeQuestionRef], list[AdvancedIssueCode]]:
    issues: list[AdvancedIssueCode] = []
    expected = _expected_subject_total()
    if quota != expected:
        if quota < expected:
            issues.append(AdvancedIssueCode.PAPER_QUOTA_SHORTAGE)
        else:
            issues.append(AdvancedIssueCode.COUNT_SURPLUS_REJECTED)

    chosen: list[PracticeQuestionRef] = []
    for subject in OFFICIAL_SUBJECTS:
        subject_quota = SYNTHETIC_SUBJECT_QUOTA_PER_PAPER[subject]
        picked = 0
        for candidate in pool.by_subject[subject]:
            if candidate.question_id in used_ids:
                continue
            if not candidate.independently_validated:
                issues.append(AdvancedIssueCode.UNVALIDATED_QUESTION)
                continue
            chosen.append(candidate)
            used_ids.add(candidate.question_id)
            picked += 1
            if picked >= subject_quota:
                break
        if picked < subject_quota:
            issues.append(AdvancedIssueCode.PAPER_QUOTA_SHORTAGE)

    if len(chosen) != expected:
        if len(chosen) < expected:
            issues.append(AdvancedIssueCode.PAPER_QUOTA_SHORTAGE)
        else:
            issues.append(AdvancedIssueCode.COUNT_SURPLUS_REJECTED)

    return chosen, issues


def assemble_synthetic_paper_items(
    *,
    paper_codes: list[str],
    pool: SyntheticFixturePool | None = None,
    requested_counts: dict[str, int] | None = None,
) -> tuple[dict[str, list[PracticeQuestionRef]], list[AdvancedIssueCode], dict[str, object]]:
    """PCM section-aware demonstration assembly; not a complete official paper."""

    fixture_pool = pool or build_synthetic_fixture_pool()
    issues: list[AdvancedIssueCode] = []
    issues.extend(validate_requested_counts(requested_counts, paper_codes=paper_codes))

    used_ids: set[str] = set()
    paper_items: dict[str, list[PracticeQuestionRef]] = {}
    section_audit: dict[str, object] = {}

    for paper_code in paper_codes:
        quota = SYNTHETIC_DEFAULT_ITEMS_PER_PAPER
        if requested_counts and paper_code in requested_counts:
            quota = requested_counts[paper_code]

        chosen, paper_issues = _select_for_paper(pool=fixture_pool, quota=quota, used_ids=used_ids)
        issues.extend(paper_issues)
        paper_items[paper_code] = chosen
        section_audit[paper_code] = {
            "requested": quota,
            "delivered": len(chosen),
            "subjects": {
                subj: sum(1 for q in chosen if q.subject_code == subj) for subj in OFFICIAL_SUBJECTS
            },
        }

    ids_per_paper = {code: [q.question_id for q in refs] for code, refs in paper_items.items()}
    all_ids = [qid for ids in ids_per_paper.values() for qid in ids]
    if len(all_ids) != len(set(all_ids)):
        issues.append(AdvancedIssueCode.DUPLICATE_CROSS_PAPER)

    return paper_items, issues, section_audit


def paper_checksum_from_items(
    paper_code: str,
    items: list[PracticeQuestionRef],
) -> str:
    payload = {
        "paper": paper_code,
        "item_ids": sorted(q.question_id for q in items),
        "subjects": sorted({q.subject_code for q in items}),
        "types": sorted(str(q.metadata_json.get("question_type", "")) for q in items),
        "assembly": "synthetic_assembled_pcm",
        "demonstration_only": True,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
