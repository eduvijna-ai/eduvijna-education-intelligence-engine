from __future__ import annotations

import hashlib
import json
from typing import Any


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def plan_checksum(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_hex(canonical.encode("utf-8"))
