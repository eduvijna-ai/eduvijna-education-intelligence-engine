from __future__ import annotations

import json

from app.prerequisite_intelligence.authority import RevisionAuthorityRecord
from app.prerequisite_intelligence.stable_ids import stable_audit_ref


def source_content_checksum(record: RevisionAuthorityRecord) -> str | None:
    if record.validated_checksum:
        return str(record.validated_checksum)
    if record.extracted_checksum:
        return str(record.extracted_checksum)
    return None


def mapping_evidence_checksum(
    *,
    misconception_code: str,
    candidate_concept_codes: list[str],
    source_locator: str,
    mapping_registry_version: str,
    source_revision_id: str,
    source_content_checksum: str,
) -> str:
    payload = json.dumps(
        {
            "misconception_code": misconception_code,
            "candidate_concept_codes": sorted(str(code) for code in candidate_concept_codes),
            "source_locator": source_locator.strip(),
            "mapping_registry_version": mapping_registry_version,
            "source_revision_id": source_revision_id,
            "source_content_checksum": source_content_checksum,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return stable_audit_ref("root-cause-mapping-evidence", payload)
