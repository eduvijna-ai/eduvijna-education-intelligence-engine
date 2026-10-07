"""Structured Day 5 official evidence report; expected gaps never abort reporting."""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from sqlalchemy.orm import Session

from app.curriculum_intelligence.day5_manifest_evidence import (
    classify_manifest_entry,
    validate_manifest_identity,
    validate_required_manifest_contract,
)
from app.curriculum_intelligence.scoped_acceptance import _revision, evaluate_day5_acceptance
from app.curriculum_intelligence.scoped_catalogue import ScopedCatalogueError
from app.curriculum_intelligence.scoped_curriculum import ScopeError
from app.curriculum_intelligence.service import (
    CurriculumIntelligenceError,
    CurriculumIntelligenceService,
    load_source_manifest,
)
from app.curriculum_intelligence.telangana_official import (
    load_verification_slice,
    official_telangana_demonstration,
)
from app.curriculum_intelligence.telangana_syllabus import TelanganaSyllabusParseError
from app.repo_paths import curricula_content_dir
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage

_EXPECTED_EVIDENCE_ERRORS = (
    ScopeError,
    ScopedCatalogueError,
    TelanganaSyllabusParseError,
    ValueError,
)


class _Links(HTMLParser):
    def __init__(self, base: str) -> None:
        super().__init__()
        self.base = base
        self.links: list[dict[str, str]] = []
        self.href: str | None = None
        self.label: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.label = []

    def handle_data(self, data: str) -> None:
        if self.href:
            self.label.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.href:
            self.links.append(
                {"url": urljoin(self.base, self.href), "label": " ".join(self.label).strip()[:160]}
            )
            self.href = None


def _empty_demonstration() -> dict[str, Any]:
    return {
        "materialized_slices": [],
        "catalogue_inventories": [],
        "unresolved_materialization": [],
        "queries": {},
        "materialization_status": "not_attempted",
    }


def _slice_task_map(scope: dict[str, Any]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for item in scope.get("required_detailed_slices", []):
        key = str(item.get("key"))
        mapping[key] = ["D5-12", "D5-13", "D5-14", "D5-22"]
    for blocked in scope.get("blocked_sources", []):
        for task in blocked.get("affected_tasks", []):
            mapping.setdefault(str(blocked.get("url")), []).append(str(task))
    return mapping


def _catalogue_gaps(report: dict[str, Any]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    inventories = report.get("catalogue_inventories") or []
    for pack_code in ("ts-scert", "tgbie"):
        official = [
            item
            for item in inventories
            if item.get("pack_code") == pack_code
            and item.get("inventory_kind") == "official_catalogue"
        ]
        if not official:
            gaps.append(
                {
                    "pack_code": pack_code,
                    "reason": "No complete official catalogue inventory materialized",
                    "affected_tasks": ["D5-09", "D5-10", "D5-22"],
                }
            )
            continue
        if not any((item.get("coverage") or {}).get("status") == "complete" for item in official):
            gaps.append(
                {
                    "pack_code": pack_code,
                    "reason": "Official catalogue inventory incomplete or unverified",
                    "affected_tasks": ["D5-09", "D5-10", "D5-22"],
                }
            )
    return gaps


def build_official_report(session: Session, *, storage_root: Path) -> dict[str, Any]:
    content_root = curricula_content_dir()
    service = CurriculumIntelligenceService(
        session,
        source_service=SourceIntelligenceService(
            session,
            storage=LocalSourceStorage(storage_root),
        ),
    )
    scope = json.loads((content_root / "day5_scope.json").read_text(encoding="utf-8"))
    verification_slice = load_verification_slice(content_root)
    entries_raw = load_source_manifest(content_root / "day5_official_sources.json")
    entries, manifest_identity_blockers = validate_manifest_identity(entries_raw)
    frozen_required, manifest_contract_blockers = validate_required_manifest_contract(
        entries, scope
    )
    manifest_identity_blockers.extend(manifest_contract_blockers)
    manifest_classification_blockers: list[dict[str, Any]] = []
    entry_roles: dict[str, str] = {}
    for entry in entries:
        role, conflict = classify_manifest_entry(entry, scope)
        entry_roles[entry.key] = role
        if conflict is not None:
            manifest_classification_blockers.append(
                {
                    "stage": "manifest_classification",
                    "source_key": conflict.source_key,
                    "url": conflict.url,
                    "reason": conflict.reason,
                    "affected_tasks": ["D5-03", "D5-05"],
                }
            )

    fetch_blockers: list[dict[str, Any]] = []
    supplemental_retrieval: list[dict[str, Any]] = []
    revisions: dict[str, Any] = {}
    required_entries = [
        entry for entry in entries if entry_roles.get(entry.key) == "required_academic"
    ]
    supplemental_entries = [
        entry for entry in entries if entry_roles.get(entry.key) == "supplemental_authority"
    ]
    for entry in entries:
        supplemental = entry_roles.get(entry.key) == "supplemental_authority"
        automated_fetch_blocked = entry.metadata_json.get("automated_fetch_blocked") is True
        if automated_fetch_blocked:
            blocker = {
                "stage": "official_retrieval",
                "source_key": entry.key,
                "url": entry.url,
                "reason": "Automated retrieval denied; manual official upload required",
                "affected_tasks": ["D5-03", "D5-05"],
            }
            if supplemental:
                supplemental_retrieval.append(blocker)
            else:
                fetch_blockers.append(blocker)
        try:
            revisions.update(
                service.ensure_manifest_sources(
                    [entry],
                    actor_id="day5-official-verifier",
                    fetch_content=not automated_fetch_blocked,
                    fallback_on_fetch_error=True,
                    request_id="day5-official-evidence",
                )
            )
        except Exception as exc:
            if not session.is_active:
                session.rollback()
            blocker = {
                "stage": "manifest_registration",
                "source_key": entry.key,
                "url": entry.url,
                "error_type": type(exc).__name__,
                "reason": str(exc)[:500],
                "affected_tasks": ["D5-03", "D5-04", "D5-05"],
            }
            if supplemental:
                supplemental_retrieval.append(blocker)
            else:
                fetch_blockers.append(blocker)

    sources: list[dict[str, Any]] = []
    unresolved_applicability: list[dict[str, Any]] = []
    for entry in entries:
        evidence_role = entry_roles[entry.key]
        supplemental = evidence_role == "supplemental_authority"
        revision = revisions.get(entry.key) if revisions else None
        verified = bool(revision and service.has_source_content(revision))
        registry_only = bool(revision and service.is_registry_only(revision))
        source_metadata = (
            dict(revision.source.metadata_json or {})
            if revision is not None and revision.source is not None
            else {}
        )
        applicability_verified = False
        if supplemental:
            applicability_verified = False
        elif verified and revision is not None:
            try:
                _revision(service, revision.id, inventory=True)
                applicability_verified = True
            except (ValueError, OSError):
                pass
        ingestion_error = source_metadata.get("ingestion_error")
        item: dict[str, Any] = {
            "key": entry.key,
            "url": entry.url,
            "domain": entry.document_type,
            "evidence_role": evidence_role,
            "source_revision_id": revision.id if revision else None,
            "checksum": revision.checksum if revision else None,
            "retrieved_content": verified,
            "byte_size": revision.byte_size if revision else None,
            "registry_only": registry_only,
            "publication_status": entry.metadata_json.get("publication_status"),
            "academic_applicability_required": not supplemental,
            "academic_applicability_verified": applicability_verified if not supplemental else None,
            "reason": None
            if verified
            else str(ingestion_error or "Official content unavailable; metadata is not evidence"),
            "ingestion_error": ingestion_error,
        }
        if (
            verified
            and revision
            and revision.content_type
            in {
                "text/html",
                "application/xhtml+xml",
            }
        ):
            data = service.source_service.storage.read(revision.storage_path or "")
            parser = _Links(entry.url)
            parser.feed(data.decode("utf-8", errors="strict"))
            item["discovered_links"] = parser.links
        sources.append(item)
        if supplemental:
            continue
        if not item["academic_applicability_verified"]:
            unresolved_applicability.append(
                {
                    "source_key": entry.key,
                    "url": entry.url,
                    "publication_status": item["publication_status"],
                    "reason": "No governing applicability notice verified from exact source bytes",
                    "affected_tasks": ["D5-02", "D5-11", "D5-31"],
                }
            )

    demonstration = _empty_demonstration()
    materialization_blockers: list[dict[str, Any]] = []
    if revisions:
        try:
            demonstration = official_telangana_demonstration(
                service,
                revisions,
                content_root=content_root,
            )
            demonstration["materialization_status"] = "attempted"
        except (*_EXPECTED_EVIDENCE_ERRORS, CurriculumIntelligenceError) as exc:
            materialization_blockers.append(
                {
                    "stage": "telangana_official_materialization",
                    "error_type": type(exc).__name__,
                    "reason": str(exc)[:500],
                    "affected_tasks": ["D5-09", "D5-10", "D5-12", "D5-13", "D5-14", "D5-22"],
                }
            )
            demonstration = _empty_demonstration()
            demonstration["materialization_status"] = "blocked"

    blocked_sources_map: dict[str, dict[str, Any]] = {
        str(item.get("url")): dict(item) for item in scope.get("blocked_sources", [])
    }
    for source in sources:
        if source["retrieved_content"] or source.get("evidence_role") == "supplemental_authority":
            continue
        blocked_sources_map[source["url"]] = {
            "url": source["url"],
            "reason": source.get("reason") or "Official bytes unavailable",
            "source_key": source["key"],
            "affected_tasks": ["D5-03", "D5-05"],
        }
    blocked_sources = list(blocked_sources_map.values())

    required_sources = [
        item for item in sources if item.get("evidence_role") == "required_academic"
    ]
    supplemental_sources = [
        item for item in sources if item.get("evidence_role") == "supplemental_authority"
    ]
    manifest_accounting = {
        "manifest_total": len(entries_raw),
        "manifest_validated_distinct": len(entries),
        "required_academic_expected_count": len(frozen_required),
        "required_academic_count": len(frozen_required),
        "required_academic_present_count": len(required_entries),
        "supplemental_authority_count": len(supplemental_entries),
        "required_academic_retrieved": sum(
            1 for item in required_sources if item["retrieved_content"]
        ),
        "required_academic_registry_only": sum(
            1 for item in required_sources if item["registry_only"]
        ),
        "supplemental_authority_retrieved": sum(
            1 for item in supplemental_sources if item["retrieved_content"]
        ),
        "supplemental_authority_registry_only": sum(
            1 for item in supplemental_sources if item["registry_only"]
        ),
        "denominator_note": (
            "Academic acceptance uses the independently frozen required_academic_count; "
            "submitted-manifest shrinkage cannot reduce that denominator, and supplemental "
            "authority directories never establish curriculum membership"
        ),
    }

    session.commit()
    report: dict[str, Any] = {
        "status": "blocked_or_review_required",
        "official_source_backed_acceptance": False,
        "sources": sources,
        "manifest_accounting": manifest_accounting,
        "required_slices": scope["required_detailed_slices"],
        "blocked_sources": blocked_sources,
        "fetch_blockers": fetch_blockers,
        "manifest_identity_blockers": manifest_identity_blockers,
        "manifest_classification_blockers": manifest_classification_blockers,
        "supplemental_retrieval": supplemental_retrieval,
        "unresolved_applicability": unresolved_applicability,
        "materialization_blockers": materialization_blockers,
        "materialized_slices": demonstration.get("materialized_slices", []),
        "extracted_slices": demonstration.get("extracted_slices", []),
        "catalogue_inventories": demonstration.get("catalogue_inventories", []),
        "catalogue_gaps": [],
        "unresolved_materialization": demonstration.get("unresolved_materialization", []),
        "queries": demonstration.get("queries", {}),
        "materialization_status": demonstration.get("materialization_status", "not_attempted"),
        "acceptance": {
            "passed": False,
            "reason": "Official Telangana evidence incomplete or unverified",
        },
        "public_artifact_contains": "metadata, checksums, URLs and blockers; no source documents",
        "task_slice_map": _slice_task_map(scope),
    }
    report["catalogue_gaps"] = _catalogue_gaps(report)
    report["acceptance"] = evaluate_day5_acceptance(
        report,
        scope,
        verification_slice=verification_slice,
        service=service,
    )
    report["official_source_backed_acceptance"] = report["acceptance"]["passed"]
    if report["official_source_backed_acceptance"]:
        report["status"] = "official_source_backed"
    return report
