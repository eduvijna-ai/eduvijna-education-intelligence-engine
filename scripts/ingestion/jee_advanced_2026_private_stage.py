#!/usr/bin/env python3
"""Local-only private staging for JEE Advanced 2026 six-slot manifest (Issue #39)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.db.base import Base
from app.db.session import create_database_engine
from app.jee_advanced.source_ingest_staging import (
    build_redacted_inventory,
    curator_handback_pending_actions,
    stage_all_official_slots_private,
)
from app.source_intelligence.storage import LocalSourceStorage
from sqlalchemy.orm import Session


def main() -> int:
    storage_root = BACKEND / "data" / "private" / "jee_advanced_2026_staging"
    db_path = storage_root / "staging.sqlite"
    storage_root.mkdir(parents=True, exist_ok=True)
    engine = create_database_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    storage = LocalSourceStorage(storage_root / "source_bytes")
    with Session(engine) as session:
        reports = stage_all_official_slots_private(session, storage)
        session.commit()
        inventory = build_redacted_inventory(reports)
    print(
        json.dumps(
            {
                "inventory": inventory,
                "curator_pending_actions": list(curator_handback_pending_actions()),
                "database": str(db_path),
                "storage_root": str(storage_root),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())