from __future__ import annotations

from threading import Lock


class ReplayStore:
    """D13-31: in-process idempotent replay cache (no duplicate generation on replay)."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._data: dict[str, dict[str, object]] = {}

    def get(self, key: str) -> dict[str, object] | None:
        with self._lock:
            return self._data.get(key)

    def put(self, key: str, payload: dict[str, object]) -> None:
        with self._lock:
            self._data[key] = payload

    def clear(self) -> None:
        with self._lock:
            self._data.clear()