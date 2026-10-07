"""Resolve bounded, format-specific standard locators against original bytes.

No free-form label or whole-document search is an evidence locator. Unsupported
or ambiguous selectors fail closed and require a reviewed bounded locator.
"""

from __future__ import annotations

import csv
import io
import json
import re
from html.parser import HTMLParser
from typing import Any

from docx import Document


class StandardsLocatorError(ValueError):
    pass


_HTML_HIDDEN = frozenset({"script", "style", "noscript", "template"})


def _hidden_html_element(tag: str, attrs: list[tuple[str, str | None]]) -> bool:
    attributes = dict(attrs)
    style = re.sub(r"\s+", "", attributes.get("style") or "").lower()
    return (
        tag in _HTML_HIDDEN
        or "hidden" in attributes
        or (attributes.get("aria-hidden") or "").lower() == "true"
        or bool(
            re.search(
                r"(?:^|;)(?:display:none|visibility:(?:hidden|collapse))(?:!important)?(?:;|$)",
                style,
            )
        )
    )


class _HtmlIdText(HTMLParser):
    _VOID = frozenset(
        "area base br col embed hr img input link meta param source track wbr".split()
    )
    _HIDDEN = _HTML_HIDDEN

    def __init__(self, target: str) -> None:
        super().__init__(convert_charrefs=True)
        self.target = target
        self.stack: list[str] = []
        self.hidden_stack: list[bool] = []
        self.target_depth: int | None = None
        self.matches = 0
        self.closed = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        hidden = (bool(self.hidden_stack) and self.hidden_stack[-1]) or _hidden_html_element(
            tag, attrs
        )
        ids = [value for key, value in attrs if key == "id"]
        if self.target in ids:
            self.matches += 1
            if len(ids) != 1 or tag in self._VOID or hidden:
                raise StandardsLocatorError("HTML locator must identify a visible container")
            self.target_depth = len(self.stack) + 1
        if tag not in self._VOID:
            self.stack.append(tag)
            self.hidden_stack.append(hidden)
        if self.target_depth is not None and not hidden and tag in {"p", "div", "li", "br", "tr"}:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in self._VOID:
            return
        if tag not in self.stack:
            raise StandardsLocatorError("Malformed HTML cannot prove a bounded locator")
        if self.target_depth is not None and self.stack[-1] != tag:
            raise StandardsLocatorError("Ambiguous HTML section boundary")
        index = len(self.stack) - 1 - self.stack[::-1].index(tag)
        if self.target_depth == index + 1:
            self.target_depth = None
            self.closed = True
        del self.stack[index:]
        del self.hidden_stack[index:]

    def handle_data(self, data: str) -> None:
        if self.target_depth is not None and self.hidden_stack and not self.hidden_stack[-1]:
            self.parts.append(data)


class _HtmlTableText(HTMLParser):
    """Resolve physical table coordinates without browser span expansion.

    Counting includes every raw table/row/cell/anchor, including hidden ones;
    hidden content never supplies evidence. Explicit balanced markup is required
    rather than guessing browser repairs or choosing a nested table's owner.
    """

    _VOID = _HtmlIdText._VOID
    _HIDDEN = _HtmlIdText._HIDDEN | {"template"}
    _BLOCK = frozenset({"p", "div", "li", "br", "tr", "td", "th"})

    def __init__(self, table: int, row: int, cell: int | None, anchor: int | None) -> None:
        super().__init__(convert_charrefs=True)
        self.wanted = (table, row, cell, anchor)
        self.stack: list[tuple[str, bool]] = []
        self.table = self.row = self.cell = self.anchor = 0
        self.in_table = self.in_row = self.in_cell = self.in_anchor = False
        self.target_depth: int | None = None
        self.matched = False
        self.closed = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        hidden = (bool(self.stack) and self.stack[-1][1]) or _hidden_html_element(tag, attrs)
        parent = self.stack[-1][0] if self.stack else None
        allowed_children = {
            "table": {"caption", "colgroup", "thead", "tbody", "tfoot", "tr"},
            "thead": {"tr"},
            "tbody": {"tr"},
            "tfoot": {"tr"},
            "tr": {"td", "th"},
            "colgroup": {"col"},
        }
        if (
            self.in_table
            and parent in allowed_children
            and tag not in (allowed_children[parent] | self._HIDDEN)
        ):
            raise StandardsLocatorError("Malformed HTML table structure requires browser repair")
        if tag == "table":
            if self.in_table:
                raise StandardsLocatorError("Nested HTML tables make physical ownership ambiguous")
            self.table += 1
            self.row = self.cell = self.anchor = 0
            self.in_table = True
        elif tag == "tr":
            if (
                not self.in_table
                or self.in_row
                or parent not in {"table", "thead", "tbody", "tfoot"}
            ):
                raise StandardsLocatorError("Malformed HTML table row")
            self.row += 1
            self.cell = self.anchor = 0
            self.in_row = True
        elif tag in {"td", "th"}:
            if not self.in_row or self.in_cell or parent != "tr":
                raise StandardsLocatorError("Malformed HTML table cell")
            self.cell += 1
            self.anchor = 0
            self.in_cell = True
        elif tag == "a" and self.in_cell:
            if self.in_anchor:
                raise StandardsLocatorError("Nested HTML anchors make the locator ambiguous")
            self.anchor += 1
            self.in_anchor = True
        wanted_table, wanted_row, wanted_cell, wanted_anchor = self.wanted
        target_tag = (
            "a" if wanted_anchor is not None else "cell" if wanted_cell is not None else "tr"
        )
        if (
            self.in_table
            and self.in_row
            and (wanted_cell is None or self.in_cell)
            and self.table == wanted_table
            and self.row == wanted_row
            and (wanted_cell is None or self.cell == wanted_cell)
            and (wanted_anchor is None or self.anchor == wanted_anchor)
            and (tag == target_tag or target_tag == "cell" and tag in {"td", "th"})
        ):
            if self.matched or hidden:
                raise StandardsLocatorError("HTML table locator must select one visible element")
            self.matched = True
            self.target_depth = len(self.stack) + 1
        if self.target_depth is not None and tag in self._BLOCK and not hidden:
            self.parts.append("\n")
        if tag not in self._VOID:
            self.stack.append((tag, hidden))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in self._VOID:
            raise StandardsLocatorError("Self-closing HTML containers have ambiguous boundaries")
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in self._VOID or not self.stack or self.stack[-1][0] != tag:
            raise StandardsLocatorError("Malformed HTML cannot prove physical table coordinates")
        if self.target_depth is not None and tag in self._BLOCK and not self.stack[-1][1]:
            self.parts.append("\n")
        if self.target_depth == len(self.stack):
            self.target_depth = None
            self.closed = True
        self.stack.pop()
        if tag == "table":
            self.in_table = False
        elif tag == "tr":
            self.in_row = False
        elif tag in {"td", "th"}:
            self.in_cell = False
        elif tag == "a" and self.in_cell:
            self.in_anchor = False

    def handle_data(self, data: str) -> None:
        if (
            self.in_table
            and self.stack
            and self.stack[-1][0]
            in {
                "table",
                "thead",
                "tbody",
                "tfoot",
                "tr",
                "colgroup",
            }
            and data.strip()
        ):
            raise StandardsLocatorError("Text outside an HTML table cell requires browser repair")
        if self.target_depth is not None and self.stack and not self.stack[-1][1]:
            self.parts.append(data)

    def selected_text(self) -> str:
        if self.stack or not self.matched or not self.closed or self.target_depth is not None:
            raise StandardsLocatorError("HTML table locator is absent or unbounded")
        return "".join(self.parts).strip()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StandardsLocatorError("Duplicate JSON keys make the locator ambiguous")
        result[key] = value
    return result


def resolve_standard_locator(content: bytes, content_type: str, locator: str) -> str:
    """Return only the selected section, never the whole source as a fallback.

    Indices are 1-based. Text ranges use original decoded lines; DOCX paragraphs
    include empty paragraphs. HTML uses a unique ID or physical table coordinates. JSON
    uses a non-root RFC 6901 pointer, CSV uses one row and optional column.
    """
    mime = content_type.split(";", 1)[0].strip().lower()
    if mime in {"text/plain", "text/markdown"}:
        match = re.fullmatch(r"text lines? ([1-9]\d*)(?:-([1-9]\d*))?", locator)
        if not match:
            raise StandardsLocatorError("Text locator requires an explicit bounded line range")
        lines = content.decode("utf-8-sig").splitlines()
        start, end = int(match[1]), int(match[2] or match[1])
        if not 1 <= start <= end <= len(lines):
            raise StandardsLocatorError("Text locator is outside original source lines")
        return "\n".join(lines[start - 1 : end])
    if mime in {"text/html", "application/xhtml+xml"}:
        positional = re.fullmatch(
            r"table\[([1-9]\d*)\]/tr\[([1-9]\d*)\]"
            r"(?:/cell\[([1-9]\d*)\](?:/a\[([1-9]\d*)\])?)?",
            locator,
        )
        if positional:
            table_parser = _HtmlTableText(
                int(positional[1]),
                int(positional[2]),
                int(positional[3]) if positional[3] else None,
                int(positional[4]) if positional[4] else None,
            )
            table_parser.feed(content.decode("utf-8-sig"))
            table_parser.close()
            return table_parser.selected_text()
        match = re.fullmatch(r"HTML #([^\s#]+)", locator)
        if not match:
            raise StandardsLocatorError(
                "HTML locator requires a unique ID or exact table coordinates"
            )
        parser = _HtmlIdText(match[1])
        parser.feed(content.decode("utf-8-sig"))
        parser.close()
        if parser.matches != 1 or not parser.closed or parser.target_depth is not None:
            raise StandardsLocatorError("HTML locator is absent, duplicated or unbounded")
        return "".join(parser.parts)
    if mime in {"application/json", "text/json"}:
        if not locator.startswith("JSON pointer /"):
            raise StandardsLocatorError("JSON locator requires a non-root JSON pointer")
        value = json.loads(content.decode("utf-8-sig"), object_pairs_hook=_unique_object)
        for token in locator[len("JSON pointer /") :].split("/"):
            if re.search(r"~(?![01])", token):
                raise StandardsLocatorError("Invalid JSON pointer escape")
            key = token.replace("~1", "/").replace("~0", "~")
            if isinstance(value, dict) and key in value:
                value = value[key]
            elif isinstance(value, list) and re.fullmatch(r"0|[1-9]\d*", key):
                value = value[int(key)]
            else:
                raise StandardsLocatorError("JSON pointer does not resolve")
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    if mime in {"text/csv", "application/csv"}:
        match = re.fullmatch(r"CSV row ([1-9]\d*)(?: column ([1-9]\d*))?", locator)
        if not match:
            raise StandardsLocatorError("CSV locator requires an explicit row and optional column")
        rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig")), strict=True))
        row = rows[int(match[1]) - 1]
        return row[int(match[2]) - 1] if match[2] else " | ".join(row)
    if mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        match = re.fullmatch(r"DOCX paragraph ([1-9]\d*)", locator)
        if not match:
            raise StandardsLocatorError("DOCX locator requires an explicit paragraph")
        return Document(io.BytesIO(content)).paragraphs[int(match[1]) - 1].text
    raise StandardsLocatorError("No bounded locator resolver for this source format")
