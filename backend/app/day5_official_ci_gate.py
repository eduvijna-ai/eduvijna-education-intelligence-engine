"""CI-only helper for Day 5 deferred official evidence; never greenwash defects."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SourceIdentity = tuple[str, str, str, str]

_APPROVED_REQUIRED_IDENTITIES: frozenset[SourceIdentity] = frozenset(
    {
        (
            "scert-syllabus-index",
            "https://scert.telangana.gov.in/Home.aspx/Pdf/pdf/publication/academiccalendar/"
            "Displaycontent.aspx?encry=Z+4YBPX+caUE5uiQSu6xdg%3D%3D",
            "official_syllabus",
            "syllabus_index",
        ),
        (
            "scert-ps-english-syllabus",
            "https://scert.telangana.gov.in/PDF/publication/syllabus/PS_EM.pdf",
            "official_syllabus",
            "subject_syllabus",
        ),
        (
            "scert-bs-english-syllabus",
            "https://scert.telangana.gov.in/PDF/publication/syllabus/BS_EM.pdf",
            "official_syllabus",
            "subject_syllabus",
        ),
        (
            "scert-textbooks-2025-26-draft",
            "https://scert.telangana.gov.in/DisplayImage.aspx?"
            "encry=Ytc1G1ftx++8OiL2XRvtdg%3D%3D",
            "official_authority",
            "textbook_index",
        ),
        (
            "scert-learning-outcomes-index",
            "https://scert.telangana.gov.in/Home.aspx/Pdf/pdf/publication/academiccalendar/"
            "Displaycontent.aspx?encry=SJZ%2FfnzG7N12MF87SAyR3A%3D%3D",
            "official_authority",
            "learning_outcome_index",
        ),
        (
            "scert-physical-science-handbook-x",
            "https://www.scert.telangana.gov.in/PDF/publication/moduls/Phy_HB_X_EM.pdf",
            "official_authority",
            "teacher_handbook",
        ),
        (
            "tgbie-maths-ia-annual-plan-2025-26",
            "https://tgbienew.cgg.gov.in/scannedPhotos/Circulars/Annual_Plan_Mahts-1A.pdf",
            "official_syllabus",
            "annual_plan",
        ),
        (
            "tgbie-maths-iia-annual-plan-2026-27",
            "https://tgbienew.cgg.gov.in/scannedPhotos/Circulars/"
            "Academic_Annual_Plan__Maths_IIA.pdf",
            "official_syllabus",
            "annual_plan",
        ),
        (
            "scert-textbooks-catalogue-2025-26",
            "https://www.scert.telangana.gov.in/Home.aspx/Pdf/pdf/DisplayContent.aspx?"
            "encry=ammkNW4%2Fgx+NeApstGPX+A%3D%3D",
            "official_authority",
            "textbook_index",
        ),
        (
            "scert-ps-telugu-syllabus",
            "https://scert.telangana.gov.in/PDF/publication/syllabus/PS_TM.pdf",
            "official_syllabus",
            "subject_syllabus",
        ),
        (
            "scert-bs-telugu-syllabus",
            "https://scert.telangana.gov.in/PDF/publication/syllabus/BS_TM.pdf",
            "official_syllabus",
            "subject_syllabus",
        ),
        (
            "tgbie-official-index",
            "https://tgbienew.cgg.gov.in/home.do",
            "official_authority",
            "publication_index",
        ),
        (
            "scert-learning-outcomes-posters-telugu",
            "https://scert.telangana.gov.in/pdf/publication/learningoutcomes/"
            "publicationlearningoutcomeslo-all-posterss-tm.pdf",
            "official_authority",
            "learning_outcomes",
        ),
    }
)

_APPROVED_SUPPLEMENTAL_IDENTITIES: frozenset[SourceIdentity] = frozenset(
    {
        (
            "telangana-state-directory-tgbie",
            "https://www.telangana.gov.in/state-web-directory/",
            "official_authority",
            "authority_directory",
        ),
        (
            "telangana-higher-education-tgbie",
            "https://www.telangana.gov.in/departments/higher-education/",
            "official_authority",
            "authority_directory",
        ),
    }
)

_APPROVED_REQUIRED_KEYS = frozenset(item[0] for item in _APPROVED_REQUIRED_IDENTITIES)
_APPROVED_SUPPLEMENTAL_KEYS = frozenset(
    item[0] for item in _APPROVED_SUPPLEMENTAL_IDENTITIES
)
_APPROVED_REPORT_SOURCE_BY_KEY: dict[str, tuple[str, str, str]] = {
    key: (url, document_type, "required_academic")
    for key, url, _source_type, document_type in _APPROVED_REQUIRED_IDENTITIES
}
_APPROVED_REPORT_SOURCE_BY_KEY.update(
    {
        key: (url, document_type, "supplemental_authority")
        for key, url, _source_type, document_type in _APPROVED_SUPPLEMENTAL_IDENTITIES
    }
)
_APPROVED_SLICE_KEYS = frozenset(
    {
        "scert-viii-physical-science-english",
        "scert-viii-biological-science-english",
        "scert-viii-science-telugu-correspondence",
        "intermediate-first-year-mathematics-english",
        "intermediate-second-year-mathematics-english",
        "intermediate-first-year-mathematics-telugu",
        "historical-first-year-mathematics-ia-uat",
        "scert-learning-outcomes",
        "scert-academic-standards",
    }
)
_APPROVED_PACK_CODES = frozenset({"ts-scert", "tgbie"})
_APPROVED_SCERT_GRADES = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")
_APPROVED_TGBIE_YEARS = ("First Year", "Second Year")
_APPROVED_DEFERRED_PACKAGES = frozenset(
    {
        (
            "SCERT VIII Physical/Biological Science English and corresponding Telugu "
            "governing syllabi plus applicability notice"
        ),
        (
            "Complete selected SCERT I-X official inventory snapshot with "
            "media/language/part information"
        ),
        (
            "Telangana Learning Outcomes / Academic Standards originals with "
            "class/subject/medium applicability"
        ),
        (
            "Official Intermediate First/Second Year General/Vocational catalogue and "
            "course/group applicability evidence"
        ),
        (
            "Historical Math IA plus applicable current First/Second Year mathematics "
            "syllabi/version notices, including corresponding Telugu material where required"
        ),
    }
)
_APPROVED_AUTOMATED_FETCH_BLOCKED_KEYS = frozenset(
    {
        "tgbie-maths-ia-annual-plan-2025-26",
        "tgbie-maths-iia-annual-plan-2026-27",
        "tgbie-official-index",
    }
)

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
_DEFERRED_RETRIEVAL_REASON = "Automated retrieval denied; manual official upload required"


@dataclass(frozen=True, slots=True)
class DeferredScopeContract:
    required_keys: frozenset[str]
    supplemental_keys: frozenset[str]
    slice_keys: frozenset[str]
    pack_codes: frozenset[str]


def _load_yaml_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file() or path.stat().st_size == 0:
        return None
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    return payload if isinstance(payload, dict) else None


def _founder_deferred_ds01(execution_state_path: Path) -> bool:
    state = _load_yaml_object(execution_state_path)
    if state is None:
        return False
    days = state.get("days")
    if not isinstance(days, dict):
        return False
    day5 = days.get(5)
    if not isinstance(day5, dict):
        return False
    return (
        day5.get("deferred_backlog") == "D5-DS01"
        and day5.get("deferred_backlog_status") == "DEFERRED_BY_FOUNDER"
    )


def _load_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file() or path.stat().st_size == 0:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _source_identities(records: list[Any]) -> frozenset[SourceIdentity] | None:
    identities: list[SourceIdentity] = []
    for item in records:
        if not isinstance(item, dict):
            return None
        key = item.get("key")
        url = item.get("url")
        source_type = item.get("source_type")
        document_type = item.get("document_type")
        if not all(
            isinstance(value, str) and value
            for value in (key, url, source_type, document_type)
        ):
            return None
        assert isinstance(key, str)
        assert isinstance(url, str)
        assert isinstance(source_type, str)
        assert isinstance(document_type, str)
        identities.append((key, url, source_type, document_type))
    if len(identities) != len(set(identities)):
        return None
    return frozenset(identities)


def _load_deferred_scope(scope_path: Path) -> DeferredScopeContract | None:
    scope = _load_json_object(scope_path)
    if scope is None:
        return None
    backlog = scope.get("deferred_authoritative_source_backlog")
    if not isinstance(backlog, dict):
        return None
    if backlog.get("id") != "D5-DS01" or backlog.get("status") != "DEFERRED_BY_FOUNDER":
        return None
    packages = backlog.get("evidence_packages")
    if (
        not isinstance(packages, list)
        or not all(isinstance(item, str) for item in packages)
        or len(packages) != len(_APPROVED_DEFERRED_PACKAGES)
        or frozenset(packages) != _APPROVED_DEFERRED_PACKAGES
    ):
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
    if _source_identities(required) != _APPROVED_REQUIRED_IDENTITIES:
        return None
    if _source_identities(supplemental) != _APPROVED_SUPPLEMENTAL_IDENTITIES:
        return None

    observed_slice_keys: list[str] = []
    for item in slices:
        if not isinstance(item, dict):
            return None
        key = item.get("key")
        if not isinstance(key, str) or not key or item.get("status") != "blocked":
            return None
        if item.get("source_revision") is not None or item.get("academic_version") is not None:
            return None
        observed_slice_keys.append(key)
    if (
        len(observed_slice_keys) != len(_APPROVED_SLICE_KEYS)
        or frozenset(observed_slice_keys) != _APPROVED_SLICE_KEYS
    ):
        return None

    by_code: dict[str, dict[str, Any]] = {}
    for item in packs:
        if not isinstance(item, dict):
            return None
        code = item.get("code")
        if not isinstance(code, str) or not code or code in by_code:
            return None
        by_code[code] = item
    if frozenset(by_code) != _APPROVED_PACK_CODES:
        return None
    if by_code["ts-scert"].get("academic_version") is not None:
        return None
    scert_grades = by_code["ts-scert"].get("grades")
    if not isinstance(scert_grades, list) or tuple(scert_grades) != _APPROVED_SCERT_GRADES:
        return None
    if by_code["tgbie"].get("academic_version") is not None:
        return None
    tgbie_years = by_code["tgbie"].get("years")
    if not isinstance(tgbie_years, list) or tuple(tgbie_years) != _APPROVED_TGBIE_YEARS:
        return None

    return DeferredScopeContract(
        required_keys=_APPROVED_REQUIRED_KEYS,
        supplemental_keys=_APPROVED_SUPPLEMENTAL_KEYS,
        slice_keys=_APPROVED_SLICE_KEYS,
        pack_codes=_APPROVED_PACK_CODES,
    )


def _load_structured_report(report_path: Path) -> dict[str, Any] | None:
    return _load_json_object(report_path)


def _exact_accounting(report: dict[str, Any], contract: DeferredScopeContract) -> bool:
    accounting = report.get("manifest_accounting")
    if not isinstance(accounting, dict):
        return False
    expected = len(_APPROVED_REQUIRED_IDENTITIES)
    supplemental = len(_APPROVED_SUPPLEMENTAL_IDENTITIES)
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
    if contract.required_keys != _APPROVED_REQUIRED_KEYS:
        return False
    if contract.supplemental_keys != _APPROVED_SUPPLEMENTAL_KEYS:
        return False
    return all(accounting.get(key) == value for key, value in exact_values.items())


def _exact_sources(report: dict[str, Any], contract: DeferredScopeContract) -> bool:
    sources = report.get("sources")
    if not isinstance(sources, list):
        return False
    expected_keys = _APPROVED_REQUIRED_KEYS | _APPROVED_SUPPLEMENTAL_KEYS
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

    for key, item in by_key.items():
        expected_url, expected_domain, expected_role = _APPROVED_REPORT_SOURCE_BY_KEY[key]
        if (
            item.get("url") != expected_url
            or item.get("domain") != expected_domain
            or item.get("evidence_role") != expected_role
        ):
            return False

    for key in contract.required_keys:
        item = by_key[key]
        if (
            item.get("retrieved_content") is not False
            or item.get("registry_only") is not True
            or item.get("academic_applicability_required") is not True
            or item.get("academic_applicability_verified") is not False
        ):
            return False

    for key in contract.supplemental_keys:
        item = by_key[key]
        if (
            item.get("retrieved_content") is not True
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
    if not isinstance(blockers, list):
        return False
    if len(blockers) != len(_APPROVED_AUTOMATED_FETCH_BLOCKED_KEYS):
        return False
    observed: set[str] = set()
    for item in blockers:
        if not isinstance(item, dict):
            return False
        key = item.get("source_key")
        if not isinstance(key, str) or key in observed:
            return False
        expected = _APPROVED_REPORT_SOURCE_BY_KEY.get(key)
        if (
            key not in _APPROVED_AUTOMATED_FETCH_BLOCKED_KEYS
            or key not in contract.required_keys
            or expected is None
            or item.get("url") != expected[0]
            or item.get("stage") != "official_retrieval"
            or item.get("reason") != _DEFERRED_RETRIEVAL_REASON
            or item.get("error_type") is not None
        ):
            return False
        observed.add(key)
    return observed == _APPROVED_AUTOMATED_FETCH_BLOCKED_KEYS


def _exact_unresolved_applicability(
    report: dict[str, Any], contract: DeferredScopeContract
) -> bool:
    unresolved = report.get("unresolved_applicability")
    if not isinstance(unresolved, list) or len(unresolved) != len(_APPROVED_REQUIRED_KEYS):
        return False
    keys: list[str] = []
    expected_reason = "No governing applicability notice verified from exact source bytes"
    for item in unresolved:
        if not isinstance(item, dict):
            return False
        key = item.get("source_key")
        if not isinstance(key, str):
            return False
        expected = _APPROVED_REPORT_SOURCE_BY_KEY.get(key)
        if (
            key not in contract.required_keys
            or expected is None
            or item.get("url") != expected[0]
            or item.get("reason") != expected_reason
        ):
            return False
        keys.append(key)
    return set(keys) == _APPROVED_REQUIRED_KEYS and len(keys) == len(set(keys))


def _exact_catalogue_gaps(report: dict[str, Any], contract: DeferredScopeContract) -> bool:
    gaps = report.get("catalogue_gaps")
    if not isinstance(gaps, list) or len(gaps) != len(_APPROVED_PACK_CODES):
        return False
    observed: set[str] = set()
    for item in gaps:
        if not isinstance(item, dict):
            return False
        code = item.get("pack_code")
        if not isinstance(code, str) or code in observed or code not in contract.pack_codes:
            return False
        if item.get("reason") != "No complete official catalogue inventory materialized":
            return False
        observed.add(code)
    return observed == _APPROVED_PACK_CODES


def _exact_acceptance_components(
    report: dict[str, Any], contract: DeferredScopeContract
) -> bool:
    acceptance = report.get("acceptance")
    if not isinstance(acceptance, dict) or acceptance.get("passed") is not False:
        return False
    components = acceptance.get("incomplete_components")
    if not isinstance(components, list) or not all(isinstance(item, str) for item in components):
        return False
    expected = _APPROVED_SLICE_KEYS | _DEFERRED_STATIC_COMPONENTS
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
    unresolved = report.get("unresolved_materialization")
    if not isinstance(unresolved, list) or not all(isinstance(item, str) for item in unresolved):
        return False
    if set(unresolved) != _DEFERRED_UNRESOLVED_MATERIALIZATION:
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
