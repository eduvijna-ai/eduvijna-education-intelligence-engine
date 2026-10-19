from __future__ import annotations

from app.diagnostic_intelligence.contracts import DiagnosticQuestionItem, DiagnosticQuestionOption
from app.orchestration.contracts import DraftQuestionItem


def draft_to_diagnostic_item(draft: DraftQuestionItem) -> DiagnosticQuestionItem:
    return DiagnosticQuestionItem(
        item_id=draft.item_id,
        stem_text=draft.stem_text,
        question_type=draft.question_type,
        options=[
            DiagnosticQuestionOption(
                option_key=option.option_key,
                text=option.text,
                is_correct=option.is_correct,
            )
            for option in draft.options
        ],
        source_revision_ids=list(draft.source_revision_ids),
        learning_outcome_ids=list(draft.learning_outcome_ids),
        competency_codes=list(draft.competency_codes),
        metadata_json=dict(draft.metadata_json),
    )
