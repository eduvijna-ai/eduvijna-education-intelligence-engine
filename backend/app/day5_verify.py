"""Isolated Day 5 verification; missing official evidence always exits nonzero."""

from __future__ import annotations

import argparse
import json
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import urljoin

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.curriculum_intelligence.scoped_acceptance import evaluate_day5_acceptance
from app.curriculum_intelligence.scoped_demo import seed_day5_verification
from app.curriculum_intelligence.service import CurriculumIntelligenceService, load_source_manifest
from app.curriculum_intelligence.telangana_official import (
    load_verification_slice,
    official_telangana_demonstration,
)
from app.db.base import Base
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage

ROOT = Path(__file__).resolve().parents[2] / "content" / "curricula"


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


def official_report(session: Session, *, storage_root: Path) -> dict[str, Any]:
    service = CurriculumIntelligenceService(
        session,
        source_service=SourceIntelligenceService(
            session,
            storage=LocalSourceStorage(storage_root),
        ),
    )
    entries = load_source_manifest(ROOT / "day5_official_sources.json")
    revisions = service.ensure_manifest_sources(
        entries,
        actor_id="day5-official-verifier",
        fetch_content=True,
        fallback_on_fetch_error=True,
        request_id="day5-official-evidence",
    )
    sources = []
    for entry in entries:
        revision = revisions[entry.key]
        verified = service.has_source_content(revision)
        item: dict[str, Any] = {
            "key": entry.key,
            "url": entry.url,
            "domain": entry.document_type,
            "source_revision_id": revision.id,
            "checksum": revision.checksum,
            "retrieved_content": verified,
            "byte_size": revision.byte_size,
            "registry_only": service.is_registry_only(revision),
            "publication_status": entry.metadata_json.get("publication_status"),
            "academic_applicability_verified": False,
            "reason": None
            if verified
            else "Official content unavailable; metadata is not evidence",
        }
        if verified and revision.content_type in {"text/html", "application/xhtml+xml"}:
            data = service.source_service.storage.read(revision.storage_path or "")
            parser = _Links(entry.url)
            parser.feed(data.decode("utf-8", errors="strict"))
            item["discovered_links"] = parser.links
        sources.append(item)
    scope = json.loads((ROOT / "day5_scope.json").read_text(encoding="utf-8"))
    verification_slice = load_verification_slice(ROOT)
    demonstration = official_telangana_demonstration(
        service,
        revisions,
        content_root=ROOT,
    )
    remaining_blocked = [
        blocked
        for blocked in scope.get("blocked_sources", [])
        if blocked.get("url") != "https://tgbienew.cgg.gov.in/home.do"
        or not any(
            revisions.get(key) and service.has_source_content(revisions[key])
            for key in (
                "tgbie-maths-ia-annual-plan-2025-26",
                "tgbie-maths-iia-annual-plan-2026-27",
            )
        )
    ]
    session.commit()
    report: dict[str, Any] = {
        "status": "blocked_or_review_required",
        "official_source_backed_acceptance": False,
        "sources": sources,
        "required_slices": scope["required_detailed_slices"],
        "blocked_sources": remaining_blocked,
        "materialized_slices": demonstration["materialized_slices"],
        "catalogue_inventories": demonstration["catalogue_inventories"],
        "unresolved_materialization": demonstration["unresolved_materialization"],
        "queries": demonstration["queries"],
        "acceptance": {
            "passed": False,
            "reason": "Bytes alone do not prove hierarchy, applicability or complete catalogue",
        },
        "public_artifact_contains": "metadata, checksums and URLs; no source documents",
    }
    merged_scope = _merge_scope_with_evidence(
        scope,
        verification_slice,
        demonstration["materialized_slices"],
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-official", action="store_true")
    args = parser.parse_args()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        if args.fetch_official:
            with TemporaryDirectory(prefix="day5-official-") as tmp:
                report = official_report(session, storage_root=Path(tmp))
        else:
            with TemporaryDirectory(prefix="day5-synthetic-") as tmp:
                report = seed_day5_verification(session, Path(tmp))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(1 if args.fetch_official and not report["acceptance"]["passed"] else 0)


if __name__ == "__main__":
    main()
