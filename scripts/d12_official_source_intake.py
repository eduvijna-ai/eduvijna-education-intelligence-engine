#!/usr/bin/env python3
"""Operator entrypoint: private JEE Advanced 2026 six-slot PDF intake (CORE #35)."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.jee_advanced.official_source_intake import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())