"""Isolated Day 5 verification; missing official evidence always exits nonzero."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.curriculum_intelligence.scoped_demo import seed_day5_verification
from app.day5_official_report import build_official_report
from app.db.base import Base


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-official", action="store_true")
    args = parser.parse_args()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    report: dict[str, Any]
    with Session(engine, expire_on_commit=False) as session:
        if args.fetch_official:
            with TemporaryDirectory(prefix="day5-official-") as tmp:
                report = build_official_report(session, storage_root=Path(tmp))
        else:
            with TemporaryDirectory(prefix="day5-synthetic-") as tmp:
                report = seed_day5_verification(session, Path(tmp))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.fetch_official:
        raise SystemExit(0 if report.get("acceptance", {}).get("passed") else 1)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
