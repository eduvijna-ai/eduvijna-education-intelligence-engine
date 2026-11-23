from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True, slots=True)
class StoredReplay:
    request_fingerprint: str
    result_payload: dict[str, object]


class ReplayStore:
    """In-process synthetic replay only — not durable across restart."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._data: dict[str, StoredReplay] = {}

    def get(self, key: str) -> StoredReplay | None:
        with self._lock:
            return self._data.get(key)

    def put(
        self,
        key: str,
        *,
        request_fingerprint: str,
        result_payload: dict[str, object],
    ) -> bool:
        """Store replay; return False when an existing key has a conflicting fingerprint."""

        with self._lock:
            existing = self._data.get(key)
            if existing is not None and existing.request_fingerprint != request_fingerprint:
                return False
            self._data[key] = StoredReplay(
                request_fingerprint=request_fingerprint,
                result_payload=result_payload,
            )
            return True

    def clear(self) -> None:
        with self._lock:
            self._data.clear()