from __future__ import annotations

import hashlib


def stable_digest(*parts: str) -> str:
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stable_snapshot_id(checksum: str, graph_version: str) -> str:
    return stable_digest("snapshot", graph_version, checksum)[:36]


def stable_path_id(snapshot_checksum: str, concept_ids: tuple[str, ...]) -> str:
    return stable_digest("path", snapshot_checksum, *concept_ids)[:36]


def stable_hypothesis_id(
    snapshot_checksum: str, misconception_code: str, concept_code: str, rank: int
) -> str:
    digest = stable_digest(
        "hypothesis", snapshot_checksum, misconception_code, concept_code, str(rank)
    )
    return digest[:36]


def stable_audit_ref(namespace: str, *parts: str) -> str:
    return stable_digest(namespace, *parts)[:40]
