#!/usr/bin/env python3
"""Fetch read-only GitHub issue authorities for C00 audit (audit-only snapshot)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs" / "execution" / "C00-GITHUB-AUTHORITY-SNAPSHOT.json"

ISSUES = [12, 16, 30, 33, 35, 44, 45, 52, 54, 56, 58, 60, 62]


def fetch_issue(n: int) -> dict:
    raw = subprocess.check_output(
        [
            "gh",
            "api",
            f"repos/eduvijna-ai/eduvijna-education-intelligence-engine/issues/{n}",
            "--jq",
            "{number, title, body, html_url, updated_at}",
        ],
        text=True,
    )
    return json.loads(raw)


def main() -> None:
    retrieved = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    items = []
    for n in ISSUES:
        try:
            data = fetch_issue(n)
            body = data.get("body") or ""
            items.append(
                {
                    "issue": n,
                    "title": data.get("title"),
                    "html_url": data.get("html_url"),
                    "updated_at": data.get("updated_at"),
                    "retrieved_at_utc": retrieved,
                    "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                    "body": body,
                }
            )
        except subprocess.CalledProcessError as exc:
            items.append(
                {
                    "issue": n,
                    "retrieved_at_utc": retrieved,
                    "error": str(exc),
                    "body_sha256": "UNAVAILABLE",
                    "body": "",
                }
            )
    payload = {
        "retrieved_at_utc": retrieved,
        "repository": "eduvijna-ai/eduvijna-education-intelligence-engine",
        "issues": items,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(REPO)} ({len(items)} issues)")


if __name__ == "__main__":
    main()