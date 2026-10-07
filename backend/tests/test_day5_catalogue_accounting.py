"""Synthetic extraction attacks; no official curriculum evidence is asserted."""

from types import SimpleNamespace
from typing import Any

import pytest

from app.curriculum_intelligence.scoped_catalogue import (
    CatalogueSnapshot,
    InventoryObservation,
    ScopedCatalogueError,
    materialize_catalogue,
    reconcile_coverage,
)
from app.curriculum_intelligence.telangana_catalogue import scert_textbook_catalogue_snapshot


def parse(body: str, **kwargs: Any) -> CatalogueSnapshot:
    return scert_textbook_catalogue_snapshot(
        content=body.encode(),
        source_url="https://scert.telangana.gov.in/catalogue",
        pack_id="pack",
        version_id="version",
        revision=SimpleNamespace(id="revision", checksum="a" * 64),  # type: ignore[arg-type]
        academic_year="2025-26",
        **kwargs,
    )


def table(cell: str, grade: str = "VIII", medium: str = "Telugu") -> str:
    return (
        "<table><tr><th>Class</th><th>Medium</th><th>First Language</th>"
        "<th>Maths</th></tr>"
        f"<tr><td>{grade}</td><td>{medium}</td>{cell}"
        '<td><a href="/math.pdf">Maths</a></td></tr></table>'
    )


def test_duplicate_occurrences_count_without_silent_url_deduplication() -> None:
    snapshot = parse(table('<td><a href="/tel.pdf">TEL</a><a href="/tel.pdf">TEL</a></td>'))
    assert len(snapshot.rows) == 2
    coverage = reconcile_coverage(snapshot, snapshot.rows)
    assert coverage.inventory_observation_count == 3
    assert coverage.duplicate_observation_count == 1
    assert coverage.resolved_observation_count == 2
    assert snapshot.inventory_observations[1].source_locator == "table[1]/tr[2]/cell[3]/a[2]"


@pytest.mark.parametrize(
    "cell,status",
    [
        ("<td></td>", "unresolved"),
        ("<td>Coming soon</td>", "blocked"),
        ("<td><a>Telugu</a></td>", "blocked"),
        ('<td><a href="/tel.pdf"></a></td>', "unresolved"),
        ('<td><a href="javascript:alert(1)">Telugu</a></td>', "blocked"),
    ],
)
def test_missing_resource_or_label_remains_in_denominator(cell: str, status: str) -> None:
    snapshot = parse(table(cell))
    assert snapshot.inventory_status == "partial"
    assert len(snapshot.inventory_observations) == 2
    assert snapshot.inventory_observations[0].status == status


def test_every_grade_with_missing_cells_does_not_establish_completeness() -> None:
    html = "<h1>TEXT BOOKS I TO X 2025-26</h1>"
    html += table("<td></td>", "I").replace("</table>", "")
    for grade in range(2, 11):
        html += (
            f"<tr><td>{grade}</td><td>Telugu</td><td></td>"
            f'<td><a href="/{grade}.pdf">Maths {grade}</a></td></tr>'
        )
    snapshot = parse(html + "</table>")
    assert snapshot.inventory_status == "partial"
    assert reconcile_coverage(snapshot, snapshot.rows).unresolved_observation_count == 10


def test_only_supported_inventory_links_count_and_no_discovery_title_promotes_scope() -> None:
    html = '<a href="/outside.pdf">outside</a><table><tr><td>Search result</td></tr></table>'
    snapshot = parse(html + table('<td><a href="/tel.pdf">TEL</a></td>'))
    assert len(snapshot.rows) == 2
    assert all(row.source_locator.startswith("table[2]/") for row in snapshot.rows)
    assert snapshot.inventory_status == "partial"


def test_parts_and_bilingual_status_remain_link_specific() -> None:
    snapshot = parse(
        table('<td>Bilingual <a href="/p1.pdf">Part1</a><a href="/p2.pdf">Part2</a></td>')
    )
    assert [row.book_part for row in snapshot.rows[:2]] == ["Part 1", "Part 2"]
    assert all(row.bilingual == "yes" for row in snapshot.rows[:2])
    assert snapshot.rows[0].subject_language == "unknown"
    assert all(row.curriculum_membership_effect == "none" for row in snapshot.rows)


def test_rowspan_is_explicit_scope_but_blank_cells_are_not_inherited() -> None:
    html = table('<td><a href="/tel.pdf">TEL</a></td>')
    html = html.replace("<td>VIII</td>", '<td rowspan="2">VIII</td>').replace("</table>", "")
    html += (
        '<tr><td>English</td><td><a href="/san.pdf">SAN</a></td>'
        '<td><a href="/math-em.pdf">Maths</a></td></tr></table>'
    )
    snapshot = parse(html)
    assert snapshot.rows[2].grade == "VIII"
    assert snapshot.rows[2].instructional_medium == "English"
    assert snapshot.rows[2].subject_language == "Sanskrit"
    assert snapshot.rows[2].language_role == "first"


@pytest.mark.parametrize(
    "html",
    [
        table("<td>\ufffd</td>"),
        table("<td>à°¤</td>"),
        table("<td>x</td>").replace("</tr>", "", 1),
        table("<td>x</td>")[:-8],
        table("<td>x</td>").replace("<td>VIII</td>", '<td rowspan="99">VIII</td>'),
    ],
)
def test_malformed_or_corrupt_inventory_fails_closed(html: str) -> None:
    with pytest.raises(ValueError):
        parse(html)


def test_shared_url_with_conflicting_parts_is_unresolved() -> None:
    snapshot = parse(table('<td><a href="/same.pdf">Part1</a><a href="/same.pdf">Part2</a></td>'))
    assert snapshot.inventory_observations[1].status == "unresolved"


def test_inventory_digest_is_registration_order_independent() -> None:
    snapshot = parse(table('<td><a href="/tel.pdf">TEL</a></td>'))
    changed_rows = tuple(
        row.model_copy(update={"pack_id": "new", "version_id": "new", "source_revision_id": "new"})
        for row in snapshot.rows
    )
    observations = tuple(
        item.model_copy(update={"row_identity": changed_rows[index].identity})
        for index, item in enumerate(snapshot.inventory_observations)
    )
    changed = snapshot.model_copy(
        update={
            "rows": changed_rows,
            "source_revision_id": "new",
            "inventory_observations": observations,
        }
    )
    assert snapshot.inventory_digest == changed.inventory_digest


def test_complete_inventory_cannot_hide_unresolved_observation() -> None:
    snapshot = parse(table('<td><a href="/tel.pdf">TEL</a></td>'))
    data = snapshot.model_dump(mode="json")
    data["inventory_status"] = "complete"
    data["inventory_observations"].append(
        InventoryObservation(
            source_locator="missing", status="unresolved", reason="missing cell"
        ).model_dump()
    )
    with pytest.raises(ValueError, match="unresolved/blocked"):
        CatalogueSnapshot.model_validate(data)


def test_superseded_catalogue_write_rejected_before_storage_or_mutation() -> None:
    snapshot = parse(table('<td><a href="/tel.pdf">TEL</a></td>'))
    version = SimpleNamespace(status="superseded", metadata_json={"preserve": True})
    with pytest.raises(ScopedCatalogueError, match="read-only"):
        materialize_catalogue(None, version, None, snapshot)  # type: ignore[arg-type]
    assert version.metadata_json == {"preserve": True}


def test_explicit_complete_inventory_requires_title_year_and_no_missing_cells() -> None:
    html = "<h1>TEXT BOOKS I TO X 2025-26</h1><table><tr><th>Class</th>"
    html += "<th>Medium</th><th>First Language</th><th>Maths</th></tr>"
    for grade in range(1, 11):
        html += (
            f"<tr><td>{grade}</td><td>Telugu</td>"
            f'<td><a href="/{grade}-tel.pdf">TEL</a></td>'
            f'<td><a href="/{grade}-math.pdf">Maths</a></td></tr>'
        )
    html += "</table>"
    snapshot = parse(html)
    assert snapshot.inventory_status == "complete"
    assert reconcile_coverage(snapshot, snapshot.rows).inventory_observation_count == 20
    assert (
        parse(html.replace("<h1>TEXT BOOKS I TO X 2025-26</h1>", "")).inventory_status == "partial"
    )


def test_ambiguous_other_media_and_second_language_remain_separate_dimensions() -> None:
    html = table('<td><a href="/hin.pdf">HIN</a></td>', medium="Other Media")
    snapshot = parse(html.replace("First Language", "Second Language"))
    row = snapshot.rows[0]
    assert row.instructional_medium == "Other Media"
    assert row.subject_language == "Hindi"
    assert row.language_role == "second"


def test_rowspan_headers_are_not_misread_as_resource_rows() -> None:
    html = (
        '<table><tr><th rowspan="2">Class</th><th rowspan="2">Medium</th>'
        "<th>First Language</th><th>Maths</th></tr>"
        "<tr><th>Language book</th><th>Mathematics book</th></tr>"
        '<tr><td>VIII</td><td>Telugu</td><td><a href="/tel.pdf">TEL</a></td>'
        '<td><a href="/math.pdf">Maths</a></td></tr></table>'
    )
    snapshot = parse(html)
    assert len(snapshot.inventory_observations) == 2
    assert snapshot.rows[0].source_locator == "table[1]/tr[3]/cell[3]/a[1]"


@pytest.mark.parametrize("tamper", ["bytes", "metadata", "approval", "grade", "version"])
def test_scoped_catalogue_rechecks_inventory_source_before_write(tamper: str) -> None:
    import hashlib
    from unittest.mock import MagicMock

    html = table('<td><a href="/tel.pdf">TEL</a></td>')
    snapshot = parse(html)
    content = html.encode()
    checksum = hashlib.sha256(content).hexdigest()
    rows = tuple(row.model_copy(update={"source_checksum": checksum}) for row in snapshot.rows)
    snapshot = snapshot.model_copy(update={"source_checksum": checksum, "rows": rows})
    service = MagicMock()
    service.has_source_content.return_value = True
    service.source_service.storage.read.return_value = b"changed" if tamper == "bytes" else content
    service.source_service._snapshot_checksum.return_value = (
        "bad" if tamper == "metadata" else "meta"
    )
    service.source_service._approval_fingerprint.return_value = (
        "bad" if tamper == "approval" else "ok"
    )
    service._source_metadata.return_value = {
        "inventory_scope": {
            "pack_code": "pack",
            "version_codes": ["different" if tamper == "version" else "version"],
            "grades": ["IX" if tamper == "grade" else "VIII"],
            "media": ["Telugu"],
        }
    }
    revision = SimpleNamespace(
        id="revision",
        checksum=checksum,
        byte_size=len(content),
        status="active",
        storage_path="private",
        extracted_text=html,
        source_snapshot_checksum="meta",
        approval_fingerprint="ok",
        metadata_json={"source_snapshot": {}},
    )
    version = SimpleNamespace(
        id="version",
        curriculum_pack_id="pack",
        version_code="version",
        academic_year="2025-26",
        curriculum_pack=SimpleNamespace(code="pack"),
        status="draft",
        metadata_json={"scope_enforced": True},
    )
    with pytest.raises(ValueError):
        materialize_catalogue(service, version, revision, snapshot)
    service.session.flush.assert_not_called()
    assert version.metadata_json == {"scope_enforced": True}
