"""Isolated Day 5 verification; missing official evidence always exits nonzero."""

from __future__ import annotations

import argparse
import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.curriculum_intelligence.service import CurriculumIntelligenceService, load_source_manifest
from app.db.base import Base

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


def official_report(session: Session) -> dict[str, Any]:
    service = CurriculumIntelligenceService(session)
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
            # URLs/short inventory labels only, never full source HTML or PDF.
            data = service.source_service.storage.read(revision.storage_path or "")
            parser = _Links(entry.url)
            parser.feed(data.decode("utf-8", errors="strict"))
            item["discovered_links"] = parser.links
        sources.append(item)
    scope = json.loads((ROOT / "day5_scope.json").read_text(encoding="utf-8"))
    session.commit()
    return {
        "status": "blocked_or_review_required",
        "official_source_backed_acceptance": False,
        "sources": sources,
        "required_slices": scope["required_detailed_slices"],
        "blocked_sources": scope["blocked_sources"],
        "acceptance": {
            "passed": False,
            "reason": "Bytes alone do not prove hierarchy, applicability or complete catalogue",
        },
        "public_artifact_contains": "metadata, checksums and URLs; no source documents",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-official", action="store_true")
    args = parser.parse_args()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        if args.fetch_official:
            report = official_report(session)
        else:
            # Populated generic verification added alongside scoped contracts.
            report = {
                "status": "implementation_in_progress",
                "official_source_backed_acceptance": False,
            }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(
        1 if args.fetch_official or report["status"] == "implementation_in_progress" else 0
    )


if __name__ == "__main__":
    main()
