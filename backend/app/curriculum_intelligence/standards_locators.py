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


class _HtmlIdText(HTMLParser):
    _VOID = frozenset(
        "area base br col embed hr img input link meta param source track wbr".split()
    )
    _HIDDEN = frozenset({"script", "style", "noscript"})

    def __init__(self, target: str) -> None:
        super().__init__(convert_charrefs=True)
        self.target = target
        self.stack: list[str] = []
        self.target_depth: int | None = None
        self.matches = 0
        self.closed = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ids = [value for key, value in attrs if key == "id"]
        if self.target in ids:
            self.matches += 1
            if len(ids) != 1 or tag in self._VOID or tag in self._HIDDEN:
                raise StandardsLocatorError("HTML locator must identify a visible container")
            self.target_depth = len(self.stack) + 1
        if tag not in self._VOID:
            self.stack.append(tag)
        if self.target_depth is not None and tag in {"p", "div", "li", "br", "tr"}:
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

    def handle_data(self, data: str) -> None:
        if self.target_depth is not None and not self._HIDDEN.intersection(self.stack):
            self.parts.append(data)


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
    include empty paragraphs. HTML requires a unique explicit container ID. JSON
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
        match = re.fullmatch(r"HTML #([^\s#]+)", locator)
        if not match:
            raise StandardsLocatorError("HTML locator requires a unique explicit container ID")
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
