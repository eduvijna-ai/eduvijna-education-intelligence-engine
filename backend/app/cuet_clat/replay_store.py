from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from threading import Condition, Lock


class ReplayAcquireStatus(StrEnum):
    CACHE_HIT = "cache_hit"
    GENERATE = "generate"
    STALE_REPLAY = "stale_replay"


@dataclass(frozen=True, slots=True)
class ReplayAcquire:
    status: ReplayAcquireStatus
    result_payload: dict[str, object] | None = None


@dataclass(slots=True)
class _ReplaySlot:
    fingerprint: str
    result_payload: dict[str, object] | None = None
    generating: bool = False


@dataclass(frozen=True, slots=True)
class StoredReplay:
    """Backward-compatible view for tests that read the store directly."""

    request_fingerprint: str
    result_payload: dict[str, object]


class ReplayStore:
    """In-process synthetic replay only — atomic claim/compare/publish per key."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._cv = Condition(self._lock)
        self._slots: dict[str, _ReplaySlot] = {}

    def get(self, key: str) -> StoredReplay | None:
        with self._lock:
            slot = self._slots.get(key)
            if slot is None or slot.result_payload is None:
                return None
            return StoredReplay(
                request_fingerprint=slot.fingerprint,
                result_payload=slot.result_payload,
            )

    def acquire(
        self,
        key: str,
        fingerprint: str,
        *,
        wait_timeout: float = 30.0,
    ) -> ReplayAcquire:
        with self._cv:
            deadline = time.monotonic() + wait_timeout
            while True:
                slot = self._slots.get(key)
                if slot is None:
                    self._slots[key] = _ReplaySlot(fingerprint=fingerprint, generating=True)
                    return ReplayAcquire(ReplayAcquireStatus.GENERATE)

                if slot.result_payload is not None:
                    if slot.fingerprint == fingerprint:
                        return ReplayAcquire(
                            ReplayAcquireStatus.CACHE_HIT,
                            dict(slot.result_payload),
                        )
                    return ReplayAcquire(ReplayAcquireStatus.STALE_REPLAY)

                if slot.generating:
                    if slot.fingerprint != fingerprint:
                        return ReplayAcquire(ReplayAcquireStatus.STALE_REPLAY)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return ReplayAcquire(ReplayAcquireStatus.STALE_REPLAY)
                    self._cv.wait(timeout=remaining)
                    continue

                self._slots[key] = _ReplaySlot(fingerprint=fingerprint, generating=True)
                return ReplayAcquire(ReplayAcquireStatus.GENERATE)

    def publish(self, key: str, fingerprint: str, result_payload: dict[str, object]) -> bool:
        with self._cv:
            slot = self._slots.get(key)
            if slot is None:
                return False
            if slot.result_payload is not None:
                return slot.fingerprint == fingerprint
            if not slot.generating or slot.fingerprint != fingerprint:
                return False
            slot.result_payload = dict(result_payload)
            slot.generating = False
            self._cv.notify_all()
            return True

    def abort_generation(self, key: str, fingerprint: str) -> None:
        with self._cv:
            slot = self._slots.get(key)
            if slot is not None and slot.generating and slot.fingerprint == fingerprint:
                del self._slots[key]
                self._cv.notify_all()

    def put(
        self,
        key: str,
        *,
        request_fingerprint: str,
        result_payload: dict[str, object],
    ) -> bool:
        """Legacy helper; prefer acquire/publish."""

        acq = self.acquire(key, request_fingerprint, wait_timeout=0.01)
        if acq.status is ReplayAcquireStatus.CACHE_HIT:
            return acq.result_payload == result_payload
        if acq.status is ReplayAcquireStatus.STALE_REPLAY:
            return False
        return self.publish(key, request_fingerprint, result_payload)

    def clear(self) -> None:
        with self._cv:
            self._slots.clear()
            self._cv.notify_all()