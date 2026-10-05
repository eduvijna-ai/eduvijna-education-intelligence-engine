"""Structured Day 5 official evidence report; expected gaps never abort reporting."""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from sqlalchemy.orm import Session

from app.curriculum_intelligence.scoped_acceptance import evaluate_day5_acceptance
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


def _merge_scope_with_evidence(
    scope: dict[str, Any],
    verification_slice: dict[str, Any],
    materialized: list[dict[str, Any]],
) -> dict[str, Any]:
    merged: dict[str, Any] = json.loads(json.dumps(scope))
    observations = {item["key"]: item for item in materialized}
    for required in merged.get("required_detailed_slices", []):
        key = required.get("key")
        if key in verification_slice.get("blocked_slice_keys", []):
            continue
        meta = verification_slice.get("slices", {}).get(key, {})
        if meta.get("chapter"):
            required["chapter"] = meta["chapter"]
        item = observations.get(key)
        if item:
            required["source_revision"] = item.get("source_revision_id")
            required["academic_version"] = item.get("academic_version")
    return merged


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
    entries = load_source_manifest(content_root / "day5_official_sources.json")

    fetch_blockers: list[dict[str, Any]] = []
    revisions: dict[str, Any] = {}
    try:
        revisions = service.ensure_manifest_sources(
            entries,
            actor_id="day5-official-verifier",
            fetch_content=True,
            fallback_on_fetch_error=True,
            request_id="day5-official-evidence",
        )
    except Exception as exc:
        fetch_blockers.append(
            {
                "stage": "manifest_registration",
                "error_type": type(exc).__name__,
                "reason": str(exc)[:500],
                "affected_tasks": ["D5-03", "D5-04", "D5-05"],
            }
        )

    sources: list[dict[str, Any]] = []
    unresolved_applicability: list[dict[str, Any]] = []
    for entry in entries:
        revision = revisions.get(entry.key) if revisions else None
        verified = bool(revision and service.has_source_content(revision))
        registry_only = bool(revision and service.is_registry_only(revision))
        item: dict[str, Any] = {
            "key": entry.key,
            "url": entry.url,
            "domain": entry.document_type,
            "source_revision_id": revision.id if revision else None,
            "checksum": revision.checksum if revision else None,
            "retrieved_content": verified,
            "byte_size": revision.byte_size if revision else None,
            "registry_only": registry_only,
            "publication_status": entry.metadata_json.get("publication_status"),
            "academic_applicability_verified": False,
            "reason": None
            if verified
            else "Official content unavailable; metadata is not evidence",
        }
        if verified and revision and revision.content_type in {
            "text/html",
            "application/xhtml+xml",
        }:
            data = service.source_service.storage.read(revision.storage_path or "")
            parser = _Links(entry.url)
            parser.feed(data.decode("utf-8", errors="strict"))
            item["discovered_links"] = parser.links
        sources.append(item)
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
        if source["retrieved_content"]:
            continue
        blocked_sources_map[source["url"]] = {
            "url": source["url"],
            "reason": source.get("reason") or "Official bytes unavailable",
            "source_key": source["key"],
            "affected_tasks": ["D5-03", "D5-05"],
        }
    blocked_sources = list(blocked_sources_map.values())

    session.commit()
    report: dict[str, Any] = {
        "status": "blocked_or_review_required",
        "official_source_backed_acceptance": False,
        "sources": sources,
        "required_slices": scope["required_detailed_slices"],
        "blocked_sources": blocked_sources,
        "fetch_blockers": fetch_blockers,
        "unresolved_applicability": unresolved_applicability,
        "materialization_blockers": materialization_blockers,
        "materialized_slices": demonstration.get("materialized_slices", []),
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
    merged_scope = _merge_scope_with_evidence(
        scope,
        verification_slice,
        report["materialized_slices"],
    )
    report["acceptance"] = evaluate_day5_acceptance(
        report,
        merged_scope,
        verification_slice=verification_slice,
    )
    report["official_source_backed_acceptance"] = report["acceptance"]["passed"]
    if report["official_source_backed_acceptance"]:
        report["status"] = "official_source_backed"
    return report
