from __future__ import annotations

from app.orchestration.contracts import DraftQuestionItem, DuplicateValidationSummary


def validate_duplicates(items: list[DraftQuestionItem]) -> list[DuplicateValidationSummary]:
    seen: dict[str, str] = {}
    seen_item_ids: set[str] = set()
    summaries: list[DuplicateValidationSummary] = []
    for item in items:
        if item.item_id in seen_item_ids:
            summaries.append(
                DuplicateValidationSummary(
                    item_id=item.item_id,
                    is_duplicate=True,
                    duplicate_of_item_id=item.item_id,
                    issue_codes=["duplicate_item_id"],
                )
            )
            continue
        seen_item_ids.add(item.item_id)
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
