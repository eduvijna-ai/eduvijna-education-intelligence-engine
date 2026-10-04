"""Fail-closed Day 5 aggregate gate; synthetic and catalogue-only evidence cannot pass."""

from __future__ import annotations

from typing import Any


def evaluate_day5_acceptance(
    report: dict[str, Any],
    scope: dict[str, Any],
    *,
    verification_slice: dict[str, Any] | None = None,
) -> dict[str, Any]:
    requirements = scope.get("required_detailed_slices", [])
    evidence = report.get("materialized_slices", [])
    keys = [item.get("key") for item in requirements]
    observations = {item.get("key"): item for item in evidence}
    blocked_keys = set(
        verification_slice.get("blocked_slice_keys", []) if verification_slice else []
    )
    slice_map = verification_slice.get("slices", {}) if verification_slice else {}
    failed = []
    if not requirements or len(keys) != len(set(keys)) or len(observations) != len(evidence):
        failed.append("invalid_required_scope_or_duplicate_evidence")
    for required in requirements:
        key = required.get("key")
        if required.get("status") == "blocked" or key in blocked_keys:
            continue
        slice_meta = slice_map.get(key, {})
        item = observations.get(key, {})
        chapter = required.get("chapter") or slice_meta.get("chapter")
        academic_version = required.get("academic_version") or item.get("academic_version")
        expected_revision = required.get("source_revision") or item.get("source_revision_id")
        frozen = bool(chapter and academic_version and expected_revision)
        path = item.get("path", {})
        verified = (
            frozen
            and item.get("verified_from_persisted_entities") is True
            and item.get("synthetic") is False
            and item.get("source_revision_id") == expected_revision
            and item.get("exact_bytes_verified") is True
            and item.get("source_domain_verified") is True
            and item.get("locator_verified") is True
            and item.get("status") == "verified"
        )
        if key not in {"scert-learning-outcomes", "scert-academic-standards"}:
            node_ids = path.get("node_ids", [])
            verified = verified and len(node_ids) == len(set(node_ids)) == 7
        else:
            verified = verified and bool(item.get("persisted_entity_ids"))
        if not verified:
            failed.append(str(key))
    inventories = report.get("catalogue_inventories", [])
    if {item.get("pack_code") for item in inventories} != {"ts-scert", "tgbie"}:
        failed.append("required_catalogue_inventories")
    for item in inventories:
        counts = item.get("coverage", {})
        if not (
            item.get("source_completeness_verified") is True
            and item.get("synthetic") is False
            and counts.get("status") == "complete"
            and counts.get("snapshot_row_count", 0) > 0
            and counts.get("snapshot_row_count") == counts.get("materialized_metadata_count")
            and not any(
                counts.get(field)
                for field in ("missing_ids", "unexpected_ids", "duplicate_ids", "conflicting_ids")
            )
        ):
            failed.append(str(item.get("pack_code")) + "_catalogue")
    if report.get("blocked_sources"):
        failed.append("required_official_sources_blocked")
    return {
        "passed": not failed,
        "incomplete_components": failed,
        "verified_detailed_slice_count": sum(
            1
            for required in requirements
            if required.get("key") not in failed
            and required.get("status") != "blocked"
            and required.get("key") not in blocked_keys
        ),
        "scope": "Reviewed bounded Day 5 scope; not all curriculum content",
    }
