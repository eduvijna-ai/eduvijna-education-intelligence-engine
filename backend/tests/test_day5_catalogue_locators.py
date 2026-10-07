"""Synthetic HTML bytes prove physical catalogue locators independently of metadata."""

from types import SimpleNamespace

import pytest

from app.curriculum_intelligence.standards_locators import (
    StandardsLocatorError,
    resolve_standard_locator,
)
from app.curriculum_intelligence.telangana_catalogue import scert_textbook_catalogue_snapshot

HTML = b"""<html><body><table><tr><td>Navigation</td></tr></table>
<table><thead><tr><th>Class</th><th>Medium</th><th>Physical Science</th></tr></thead>
<tbody><tr><td rowspan="2">VIII</td><td>English</td><td>
<a href="/8EM_PHY.pdf">8EM_PHY</a><a href="/8EM_PHY_P2.pdf">Part2</a></td></tr>
<tr><td>Telugu</td><td><a href="/8TM_PHY.pdf">8TM_PHY</a></td></tr></tbody></table>
<a href="/outside">Outside</a></body></html>"""


def test_exact_raw_coordinates_match_parser_output_and_ignore_rowspan_expansion() -> None:
    snapshot = scert_textbook_catalogue_snapshot(
        content=HTML,
        source_url="https://synthetic.invalid/catalogue",
        pack_id="pack",
        version_id="version",
        revision=SimpleNamespace(id="revision", checksum="a" * 64),  # type: ignore[arg-type]
        academic_year="2025-26",
    )
    assert snapshot.rows
    for row in snapshot.rows:
        text = resolve_standard_locator(HTML, "text/html", row.source_locator)
        assert text in {"8EM_PHY", "Part2", "8TM_PHY"}
    assert resolve_standard_locator(HTML, "text/html", "table[2]/tr[3]/cell[2]/a[1]") == "8TM_PHY"
    assert resolve_standard_locator(HTML, "text/html", "table[2]/tr[2]/cell[1]") == "VIII"
    assert resolve_standard_locator(HTML, "text/html", "table[2]/tr[3]/cell[1]") == "Telugu"
    assert (
        " ".join(resolve_standard_locator(HTML, "text/html", "table[2]/tr[3]").split())
        == "Telugu 8TM_PHY"
    )
    assert resolve_standard_locator(HTML, "text/html", "table[2]/tr[2]/cell[3]/a[2]") == "Part2"


@pytest.mark.parametrize(
    "locator",
    [
        "table[3]/tr[1]",
        "table[2]/tr[9]",
        "table[2]/tr[3]/cell[3]/a[1]",
        "table[2]/tr[3]/cell[1]/a[1]",
        "table[2]/tr[2]/cell[3]/a[3]",
        "table[0]/tr[1]",
        "table[2]/tr[01]",
        "table[2]/tr[2]/a[1]",
        "table[2]/tr[2]/cell[3]/a[1]/../a[2]",
        "table[2]/tr[2-3]",
        "table[2]",
        "table[2]/tr[2]/missing-cell[3]",
    ],
)
def test_nonexistent_cross_cell_and_malformed_selectors_fail(locator: str) -> None:
    with pytest.raises(StandardsLocatorError):
        resolve_standard_locator(HTML, "text/html", locator)


@pytest.mark.parametrize(
    "content",
    [
        b"<table><tr><td><table><tr><td>Nested</td></tr></table></td></tr></table>",
        b"<table><tr><td>Unclosed</tr></table>",
        b"<table><tr><td>Unbounded",
        b"<table><td>Missing row</td></table>",
        b'<table><tr><td><a href="a">A<a href="b">B</a></a></td></tr></table>',
        b"<table><tr><td/><td>Ambiguous</td></tr></table>",
        b"<table><tr>Unowned group<td>Title</td></tr></table>",
        b"<table><tr><div>Misplaced group</div><td>Title</td></tr></table>",
    ],
)
def test_malformed_or_nested_table_boundaries_fail(content: bytes) -> None:
    with pytest.raises(StandardsLocatorError):
        resolve_standard_locator(content, "text/html", "table[1]/tr[1]/cell[1]")


def test_only_visible_text_inside_selected_element_supplies_evidence() -> None:
    content = b"""<table><tr><td><a href="/x">Visible <span>title</span>
    <script>invented course group</script><style>invented medium</style>
    <noscript>invented year</noscript><span hidden>secret</span>
    <span aria-hidden="true">concealed</span><span style="display: none">masked</span>
    <span style="visibility: hidden !important">invisible</span></a></td>
    <td>Unrelated group</td></tr></table>"""
    result = resolve_standard_locator(content, "text/html", "table[1]/tr[1]/cell[1]/a[1]")
    assert " ".join(result.split()) == "Visible title"
    assert "Unrelated" not in result


def test_hidden_elements_keep_physical_index_but_cannot_prove_evidence() -> None:
    content = b"<table><tr><td><a hidden>Hidden</a><a>Shown &amp; real</a></td></tr></table>"
    with pytest.raises(StandardsLocatorError):
        resolve_standard_locator(content, "text/html", "table[1]/tr[1]/cell[1]/a[1]")
    assert (
        resolve_standard_locator(content, "text/html", "table[1]/tr[1]/cell[1]/a[2]")
        == "Shown & real"
    )


@pytest.mark.parametrize(
    "wrapper",
    [
        "<template>{}</template>",
        "<div hidden>{}</div>",
        '<div aria-hidden="true">{}</div>',
        '<div style="display:none">{}</div>',
        '<div style="visibility:hidden">{}</div>',
    ],
)
def test_id_locator_rejects_hidden_container_or_ancestor(wrapper: str) -> None:
    for html in (
        wrapper.format('<span id="target">Hidden code</span>'),
        wrapper.replace(">", ' id="target">', 1).format("Hidden code"),
    ):
        with pytest.raises(StandardsLocatorError):
            resolve_standard_locator(html.encode(), "text/html", "HTML #target")


def test_id_locator_excludes_hidden_only_codes_and_preserves_visible_unicode() -> None:
    content = (
        '<section id="target">తెలుగు اردو '
        "<template>CODE-T</template><span hidden>CODE-H</span>"
        '<span aria-hidden="true">CODE-A</span>'
        '<span style="display:none">CODE-D</span><span>दृश्य</span></section>'
    ).encode()
    result = resolve_standard_locator(content, "text/html", "HTML #target")
    assert result == "తెలుగు اردو दृश्य"
    assert "CODE-" not in result
