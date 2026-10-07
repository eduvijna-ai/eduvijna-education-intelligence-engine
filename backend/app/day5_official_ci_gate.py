"""CI-only helper for Day 5 deferred official evidence; never greenwash defects."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_EMPTY_REQUIRED_FIELDS = (
    "manifest_identity_blockers",
    "manifest_classification_blockers",
    "materialization_blockers",
    "supplemental_retrieval",
    "materialized_slices",
    "extracted_slices",
    "catalogue_inventories",
)

_DEFERRED_STATIC_COMPONENTS = {
    "invalid_required_scope_or_duplicate_evidence",
    "required_catalogue_inventories",
    "invalid_frozen_catalogue_scope",
    "ts-scert_catalogue_scope",
    "tgbie_catalogue_scope",
    "required_official_sources_blocked",
    "fetch_blockers",
    "unresolved_applicability",
    "catalogue_gaps",
    "unresolved_materialization",
}

_DEFERRED_UNRESOLVED_MATERIALIZATION = {
    "scert-viii-physical-science-english:official_bytes_unavailable",
    "scert-viii-biological-science-english:official_bytes_unavailable",
    "scert-textbook-catalogue:governing_version_applicability_required",
    (
        "tgbie-pack:governing_syllabus_required;"
        "annual_plans_are_supporting_calendar_evidence"
    ),
}

_DEFERRED_RETRIEVAL_REASON = (
    "Automated retrieval denied; manual official upload required"
)


@dataclass(frozen=True, slots=True)
class DeferredScopeContract:
    required_keys: frozenset[str]
    supplemental_keys: frozenset[str]
    slice_keys: frozenset[str]
    pack_codes: frozenset[str]


def _founder_deferred_ds01(execution_state_path: Path) -> bool:
    if not execution_state_path.is_file():
        return False
    text = execution_state_path.read_text(encoding="utf-8")
    return (
        "deferred_backlog: D5-DS01" in text
        and "deferred_backlog_status: DEFERRED_BY_FOUNDER" in text
    )


def _load_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file() or path.stat().st_size == 0:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _load_deferred_scope(scope_path: Path) -> DeferredScopeContract | None:
    scope = _load_json_object(scope_path)
    if scope is None:
        return None
    backlog = scope.get("deferred_authoritative_source_backlog")
    if not isinstance(backlog, dict):
        return None
    if backlog.get("id") != "D5-DS01" or backlog.get("status") != "DEFERRED_BY_FOUNDER":
        return None

    required = scope.get("frozen_required_academic_sources")
    supplemental = scope.get("frozen_supplemental_authority_sources")
    slices = scope.get("required_detailed_slices")
    packs = scope.get("packs")
    if (
        not isinstance(required, list)
        or not isinstance(supplemental, list)
        or not isinstance(slices, list)
        or not isinstance(packs, list)
    ):
        return None

    def keys(records: list[Any]) -> frozenset[str] | None:
        values: list[str] = []
        for item in records:
            if not isinstance(item, dict):
                return None
            key = item.get("key")
            if not isinstance(key, str) or not key:
                return None
            values.append(key)
        if len(values) != len(set(values)):
            return None
        return frozenset(values)

    required_keys = keys(required)
    supplemental_keys = keys(supplemental)
    slice_keys = keys(slices)
    if not required_keys or supplemental_keys is None or not slice_keys:
        return None
    if required_keys & supplemental_keys:
        return None
    if any(item.get("status") != "blocked" for item in slices if isinstance(item, dict)):
        return None

    pack_codes: list[str] = []
    for item in packs:
        if not isinstance(item, dict):
            return None
        code = item.get("code")
        if not isinstance(code, str) or not code:
            return None
        pack_codes.append(code)
    if set(pack_codes) != {"ts-scert", "tgbie"}:
        return None

    return DeferredScopeContract(
        required_keys=required_keys,
        supplemental_keys=supplemental_keys,
        slice_keys=slice_keys,
        pack_codes=frozenset(pack_codes),
    )


def _load_structured_report(report_path: Path) -> dict[str, Any] | None:
    return _load_json_object(report_path)


def _exact_accounting(report: dict[str, Any], contract: DeferredScopeContract) -> bool:
    accounting = report.get("manifest_accounting")
    if not isinstance(accounting, dict):
        return False
    expected = len(contract.required_keys)
    supplemental = len(contract.supplemental_keys)
    exact_values = {
        "manifest_total": expected + supplemental,
        "manifest_validated_distinct": expected + supplemental,
        "required_academic_expected_count": expected,
        "required_academic_count": expected,
        "required_academic_present_count": expected,
        "supplemental_authority_count": supplemental,
        "required_academic_retrieved": 0,
        "required_academic_registry_only": expected,
        "supplemental_authority_retrieved": supplemental,
        "supplemental_authority_registry_only": 0,
    }
    return all(accounting.get(key) == value for key, value in exact_values.items())


def _exact_sources(report: dict[str, Any], contract: DeferredScopeContract) -> bool:
    sources = report.get("sources")
    if not isinstance(sources, list):
        return False
    expected_keys = contract.required_keys | contract.supplemental_keys
    if len(sources) != len(expected_keys):
        return False
    by_key: dict[str, dict[str, Any]] = {}
    for item in sources:
        if not isinstance(item, dict):
            return False
        key = item.get("key")
        if not isinstance(key, str) or key in by_key:
            return False
        by_key[key] = item
    if set(by_key) != expected_keys:
        return False

    for key in contract.required_keys:
        item = by_key[key]
        if (
            item.get("evidence_role") != "required_academic"
            or item.get("retrieved_content") is not False
            or item.get("registry_only") is not True
            or item.get("academic_applicability_required") is not True
            or item.get("academic_applicability_verified") is not False
        ):
            return False

    for key in contract.supplemental_keys:
        item = by_key[key]
        if (
            item.get("evidence_role") != "supplemental_authority"
            or item.get("retrieved_content") is not True
            or item.get("registry_only") is not False
            or item.get("academic_applicability_required") is not False
            or item.get("academic_applicability_verified") is not None
        ):
            return False
    return True


def _only_expected_retrieval_blockers(
    report: dict[str, Any], contract: DeferredScopeContract
) -> bool:
    blockers = report.get("fetch_blockers")
    if not isinstance(blockers, list) or not blockers:
        return False
    for item in blockers:
        if not isinstance(item, dict):
            return False
        if (
            item.get("stage") != "official_retrieval"
            or item.get("source_key") not in contract.required_keys
            or item.get("reason") != _DEFERRED_RETRIEVAL_REASON
            or item.get("error_type") is not None
        ):
            return False
    return True


def _exact_unresolved_applicability(
    report: dict[str, Any], contract: DeferredScopeContract
) -> bool:
    unresolved = report.get("unresolved_applicability")
    if not isinstance(unresolved, list) or len(unresolved) != len(contract.required_keys):
        return False
    keys: list[str] = []
    for item in unresolved:
        if not isinstance(item, dict):
            return False
        key = item.get("source_key")
        if not isinstance(key, str):
            return False
        expected_reason = (
            "No governing applicability notice verified from exact source bytes"
        )
        if item.get("reason") != expected_reason:
            return False
        keys.append(key)
    return set(keys) == contract.required_keys and len(keys) == len(set(keys))


def _exact_catalogue_gaps(report: dict[str, Any], contract: DeferredScopeContract) -> bool:
    gaps = report.get("catalogue_gaps")
    if not isinstance(gaps, list) or len(gaps) != len(contract.pack_codes):
        return False
    observed: set[str] = set()
    for item in gaps:
        if not isinstance(item, dict):
            return False
        code = item.get("pack_code")
        if code in observed or code not in contract.pack_codes:
            return False
        if item.get("reason") != "No complete official catalogue inventory materialized":
            return False
        observed.add(code)
    return observed == contract.pack_codes


def _exact_acceptance_components(
    report: dict[str, Any], contract: DeferredScopeContract
) -> bool:
    acceptance = report.get("acceptance")
    if not isinstance(acceptance, dict) or acceptance.get("passed") is not False:
        return False
    components = acceptance.get("incomplete_components")
    if not isinstance(components, list) or not all(isinstance(item, str) for item in components):
        return False
    expected = contract.slice_keys | _DEFERRED_STATIC_COMPONENTS
    return set(components) == expected and len(components) == len(set(components))


def _engineering_sound(report: dict[str, Any], contract: DeferredScopeContract) -> bool:
    if (
        report.get("status") != "blocked_or_review_required"
        or report.get("official_source_backed_acceptance") is not False
        or report.get("materialization_status") != "attempted"
        or report.get("queries") != {}
    ):
        return False
    for field in _EMPTY_REQUIRED_FIELDS:
        value = report.get(field)
        if not isinstance(value, list) or value:
            return False
    if not isinstance(report.get("public_artifact_contains"), str):
        return False
    if not _exact_accounting(report, contract):
        return False
    if not _exact_sources(report, contract):
        return False
    if not _only_expected_retrieval_blockers(report, contract):
        return False
    if not _exact_unresolved_applicability(report, contract):
        return False
    if not _exact_catalogue_gaps(report, contract):
        return False
    if set(report.get("unresolved_materialization", [])) != _DEFERRED_UNRESOLVED_MATERIALIZATION:
        return False
    if not _exact_acceptance_components(report, contract):
        return False
    return True


def _verified_success(report: dict[str, Any]) -> bool:
    acceptance = report.get("acceptance")
    return bool(
        isinstance(acceptance, dict)
        and acceptance.get("passed") is True
        and report.get("official_source_backed_acceptance") is True
        and report.get("status") == "official_source_backed"
    )


def resolve_ci_exit_code(
    verifier_exit: int,
    report_path: Path,
    *,
    execution_state_path: Path,
    scope_path: Path | None = None,
) -> int:
    """Return process exit code for the day5-official-evidence CI step."""
    report = _load_structured_report(report_path)
    if report is None:
        return verifier_exit if verifier_exit != 0 else 1
    if verifier_exit == 0:
        return 0 if _verified_success(report) else 1
    if not _founder_deferred_ds01(execution_state_path):
        return verifier_exit
    resolved_scope = scope_path or (
        Path(__file__).resolve().parents[2] / "content" / "curricula" / "day5_scope.json"
    )
    contract = _load_deferred_scope(resolved_scope)
    if contract is None or not _engineering_sound(report, contract):
        return verifier_exit
    print(
        "::warning::Day 5 authoritative source gate remains fail-closed "
        "(acceptance=false); D5-DS01 is Founder-deferred. "
        f"Verifier exit code: {verifier_exit}. Metadata artifact uploaded.",
        file=sys.stderr,
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--verifier-exit", type=int, required=True)
    parser.add_argument(
        "--execution-state",
        type=Path,
        default=Path(__file__).resolve().parents[2] / ".eduvijna" / "execution-state.yml",
    )
    parser.add_argument(
        "--scope",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "content"
        / "curricula"
        / "day5_scope.json",
    )
    args = parser.parse_args()
    raise SystemExit(
        resolve_ci_exit_code(
            args.verifier_exit,
            args.report,
            execution_state_path=args.execution_state,
            scope_path=args.scope,
        )
    )


if __name__ == "__main__":
    main()
