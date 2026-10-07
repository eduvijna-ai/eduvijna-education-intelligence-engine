from __future__ import annotations

from types import SimpleNamespace

from app.curriculum_intelligence.telangana_catalogue import (
    scert_textbook_catalogue_snapshot,
)


def _catalogue_html() -> bytes:
    header = (
        "<tr><th>Class</th><th>Medium</th><th>First Language</th>"
        "<th>Other Media</th><th>English</th><th>Maths</th>"
        "<th>Physical Science</th><th>Biological Science</th>"
        "<th>Social</th><th>Environmental Education</th></tr>"
    )
    rows: list[str] = [header]
    suffix = {8: "th", 1: "st", 2: "nd", 3: "rd"}
    for grade in range(1, 11):
        ordinal = f"{grade}{suffix.get(grade, 'th')}"
        if grade == 8:
            physical = (
                '<a href="/books/8TM_PHY_P1.pdf">Part1</a><a href="/books/8TM_PHY_P2.pdf">Part2</a>'
            )
        else:
            physical = f'<a href="/books/{grade}TM_PHY.pdf">{grade}TM_PHY</a>'
        rows.append(
            f'<tr><td rowspan="{3 if grade == 8 else 1}">{ordinal}</td><td>Telugu</td>'
            f'<td><a href="/books/{grade}_TEL.pdf">{grade}_TEL</a></td>'
            f'<td><a href="/books/{grade}_TEL_OM.pdf">{grade}_TEL(OM)</a></td>'
            f'<td><a href="/books/{grade}_ENG.pdf">{grade}_ENG</a></td>'
            f'<td><a href="/books/{grade}TM_MAT.pdf">{grade}TM_MAT</a></td>'
            f"<td>{physical}</td>"
            f'<td><a href="/books/{grade}TM_BIO.pdf">{grade}TM_BIO</a></td>'
            f'<td><a href="/books/{grade}TM_SOC.pdf">{grade}TM_SOC</a></td>'
            "<td></td></tr>"
        )
        if grade == 8:
            rows.extend(
                [
                    "<tr><td>English</td>"
                    '<td><a href="/books/8_SAN_CC.pdf">8_SAN_CC</a></td>'
                    '<td><a href="/books/8_SAN_OC.pdf">8_SAN_OC</a></td><td></td>'
                    '<td><a href="/books/8EM_MAT.pdf">8EM_MAT</a></td>'
                    '<td><a href="/books/8EM_PHY.pdf">8EM_PHY</a></td>'
                    '<td><a href="/books/8EM_BIO.pdf">8EM_BIO</a></td>'
                    '<td><a href="/books/8EM_SOC.pdf">8EM_SOC</a></td><td></td></tr>',
                    "<tr><td>Urdu</td>"
                    '<td><a href="/books/8UM_URD_FL.pdf">8UM_URD_FL</a></td>'
                    '<td><a href="/books/8UM_URD_SL.pdf">8UM_URD_SL</a></td><td></td>'
                    '<td><a href="/books/8UM_MAT.pdf">8UM_MAT</a></td>'
                    '<td><a href="/books/8UM_PHY.pdf">8UM_PHY</a></td>'
                    '<td><a href="/books/8UM_BIO.pdf">8UM_BIO</a></td>'
                    '<td><a href="/books/8UM_SOC.pdf">8UM_SOC</a></td><td></td></tr>',
                ]
            )
    return ("<html><body><table>" + "".join(rows) + "</table></body></html>").encode()


def test_scert_catalogue_accounts_for_i_to_x_media_and_parts() -> None:
    revision = SimpleNamespace(id="revision-1", checksum="a" * 64)
    snapshot = scert_textbook_catalogue_snapshot(
        content=_catalogue_html(),
        source_url="https://scert.telangana.gov.in/catalogue",
        pack_id="pack-1",
        version_id="version-1",
        revision=revision,  # type: ignore[arg-type]
        academic_year="2025-26",
    )

    assert snapshot.inventory_status == "partial"  # Empty resources stay unresolved.
    assert {row.grade for row in snapshot.rows} >= {
        "I",
        "II",
        "III",
        "IV",
        "V",
        "VI",
        "VII",
        "VIII",
        "IX",
        "X",
    }
    grade8 = [row for row in snapshot.rows if row.grade == "VIII"]
    assert {row.instructional_medium for row in grade8} >= {"Telugu", "English", "Urdu"}
    assert {row.book_part for row in grade8} >= {"Part 1", "Part 2"}
    telugu_first = next(row for row in grade8 if row.official_label == "8_TEL")
    assert telugu_first.language_role == "first"
    assert telugu_first.subject_language == "Telugu"
    sanskrit = next(row for row in grade8 if row.official_label == "8_SAN_CC")
    assert sanskrit.instructional_medium == "English"
    assert sanskrit.subject_language == "Sanskrit"


def test_scert_catalogue_is_partial_when_grade_inventory_is_incomplete() -> None:
    revision = SimpleNamespace(id="revision-1", checksum="b" * 64)
    html = (
        b"<table><tr><th>Class</th><th>Medium</th><th>First Language</th>"
        b"<th>Maths</th></tr><tr><td>8th</td><td>Telugu</td>"
        b'<td><a href="/8_TEL.pdf">8_TEL</a></td>'
        b'<td><a href="/8TM_MAT.pdf">8TM_MAT</a></td></tr></table>'
    )
    snapshot = scert_textbook_catalogue_snapshot(
        content=html,
        source_url="https://scert.telangana.gov.in/catalogue",
        pack_id="pack-1",
        version_id="version-1",
        revision=revision,  # type: ignore[arg-type]
        academic_year="2025-26",
    )
    assert snapshot.inventory_status == "partial"
