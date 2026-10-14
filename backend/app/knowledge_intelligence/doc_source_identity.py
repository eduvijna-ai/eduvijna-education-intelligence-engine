from __future__ import annotations


def build_stable_doc_source_identity(
    source_revision_id: str,
    profile_version: str,
    checksum: str,
) -> str:
    """Deterministic Eduvijna remote provenance identity (D7-PIC-01)."""
    return f"eduvijna://knowledge/{source_revision_id}/{profile_version}/{checksum}"
