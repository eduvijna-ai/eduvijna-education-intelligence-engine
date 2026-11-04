from __future__ import annotations

from enum import StrEnum


class TrustExecutionMode(StrEnum):
    """Controls whether synthetic fixture trust is permitted."""

    PRODUCTION = "production"
    SYNTHETIC_FIXTURE = "synthetic_fixture"
