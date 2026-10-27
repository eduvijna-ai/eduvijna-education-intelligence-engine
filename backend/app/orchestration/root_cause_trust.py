from __future__ import annotations

from typing import Any

from app.diagnostic_intelligence.enums import DiagnosticValidationStatus
from app.knowledge_intelligence.contracts import KnowledgeContextPack
from app.root_cause_intelligence.trusted_validation import RootCauseTrustedValidationContext


def option_allowed_source_revision_ids(
    draft_item: dict[str, Any],
    context: KnowledgeContextPack,
    tag_data: dict[str, Any],
) -> list[str]:
    draft_sources = {
        str(revision_id)
        for revision_id in (draft_item.get("source_revision_ids") or [])
        if revision_id
    }
    pack_sources = {
        str(item.source_revision_id)
        for item in context.evidence
        if item.source_revision_id
    }
    base = draft_sources & pack_sources
    evidence_refs = list(tag_data.get("evidence_refs") or [])
    if not evidence_refs:
        return []

    citation_to_revision = {
        str(item.citation_label): str(item.source_revision_id)
        for item in context.evidence
        if item.citation_label and item.source_revision_id
    }
    unknown = [ref for ref in evidence_refs if ref not in citation_to_revision]
    if unknown:
        return []
    cited_revisions = {citation_to_revision[ref] for ref in evidence_refs}
    if not cited_revisions:
        return []
    return sorted(base & cited_revisions)


def build_trusted_validation_from_state(
    *,
    item_id: str,
    option_key: str,
    misconception_code: str,
    taxonomy_version: str,
    diagnostic_validation: list[dict[str, Any]],
    diagnostic_results: list[dict[str, Any]],
) -> RootCauseTrustedValidationContext | None:
    summary = next(
        (entry for entry in diagnostic_validation if str(entry.get("item_id")) == item_id),
        None,
    )
    if summary is None or summary.get("blocking") or summary.get("review_required"):
        return None

    enriched = next(
        (entry for entry in diagnostic_results if str(entry.get("item_id")) == item_id),
        None,
    )
    if enriched is None:
        return None

    tag_entry = next(
        (
            tag
            for tag in enriched.get("option_tags") or []
            if str(tag.get("option_key")) == option_key
        ),
        None,
    )
    if tag_entry is None:
        return None

    status = tag_entry.get("validation_status")
    if status is None or str(status) != DiagnosticValidationStatus.PASS.value:
        return None

    if str(tag_entry.get("misconception_code") or "") != misconception_code:
        return None
    if str(enriched.get("taxonomy_version") or "") != taxonomy_version:
        return None

    audit_refs = list(enriched.get("audit_refs") or [])
    audit_ref = audit_refs[0] if audit_refs else None
    if not audit_ref:
        return None

    return RootCauseTrustedValidationContext.from_day9_accepted(
        item_id=item_id,
        option_key=option_key,
        misconception_code=misconception_code,
        taxonomy_version=taxonomy_version,
        day9_audit_ref=audit_ref,
    )
