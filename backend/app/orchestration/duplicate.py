from __future__ import annotations

from app.orchestration.contracts import DraftQuestionItem, DuplicateValidationSummary


def validate_duplicates(items: list[DraftQuestionItem]) -> list[DuplicateValidationSummary]:
    seen: dict[str, str] = {}
    summaries: list[DuplicateValidationSummary] = []
    for item in items:
        fingerprint = item.content_fingerprint()
        duplicate_of = seen.get(fingerprint)
        if duplicate_of is not None:
            summaries.append(
                DuplicateValidationSummary(
                    item_id=item.item_id,
                    is_duplicate=True,
                    duplicate_of_item_id=duplicate_of,
                    issue_codes=["duplicate_content"],
                )
            )
        else:
            seen[fingerprint] = item.item_id
            summaries.append(
                DuplicateValidationSummary(
                    item_id=item.item_id,
                    is_duplicate=False,
                )
            )
    return summaries
