"""Internal-only synthetic job fixture — not academic readiness."""

from __future__ import annotations

from typing import Any

SYNTHETIC_JOB_CAPABILITY = "platform.synthetic_echo"
SYNTHETIC_INTERNAL_REQUEST: dict[str, Any] = {
    "fixture_id": "day17-internal-synthetic-v1",
    "controlled": True,
}