"""Parse authoritative Day task requirements from approved specs (C00 audit-only)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class AuthorityTask:
    task_id: str
    original_authority: str
    requirement: str
    acceptance: str
    day: str


def parse_heading_tasks(
    text: str,
    pattern: re.Pattern[str],
    authority: str,
    day: str,
    acceptance_from_body: bool = True,
) -> list[AuthorityTask]:
    """### D7-01 — Title\\nbody until next ###."""
    tasks: list[AuthorityTask] = []
    chunks = re.split(r"(?=^### )", text, flags=re.MULTILINE)
    for chunk in chunks:
        m = re.match(r"^###\s+(" + pattern.pattern + r")\s*[—-]\s*(.+)$", chunk, re.MULTILINE)
        if not m:
            continue
        tid = m.group(1)
        title = m.group(2).strip()
        body = chunk.split("\n", 1)[1].strip() if "\n" in chunk else ""
        body = re.sub(r"^#+ .+$", "", body, flags=re.MULTILINE).strip()
        acc = body.split("\n\n")[0][:500] if acceptance_from_body and body else title
        tasks.append(
            AuthorityTask(tid, authority, title, acc or title, day)
        )
    return tasks


def parse_checkbox_requirements(text: str, id_re: re.Pattern[str], authority: str, day: str) -> list[AuthorityTask]:
    tasks: list[AuthorityTask] = []
    for line in text.splitlines():
        m = re.match(r"^- \[ \]\s+(" + id_re.pattern + r")\s+(.+)$", line.strip())
        if not m:
            continue
        tid = m.group(1)
        rest = m.group(2).strip()
        tasks.append(AuthorityTask(tid, authority, rest, rest, day))
    return tasks


def parse_line_title_tasks(text: str, authority: str, day: str) -> list[AuthorityTask]:
    tasks: list[AuthorityTask] = []
    for line in text.splitlines():
        m = re.match(r"^(D5-\d{2})\s+[—-]\s+(.+)$", line.strip())
        if not m:
            continue
        tasks.append(AuthorityTask(m.group(1), authority, m.group(2), m.group(2), day))
    return tasks


def parse_pipe_authoritative_table(text: str, id_prefix: str, authority: str, day: str) -> list[AuthorityTask]:
    """| **D11-01** | Task | Concrete acceptance |"""
    tasks: list[AuthorityTask] = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 3:
            continue
        tid = parts[0].strip("*").strip()
        if not tid.startswith(id_prefix):
            continue
        if set(parts[0]) <= set("-:"):
            continue
        tasks.append(AuthorityTask(tid, authority, parts[1], parts[2], day))
    return tasks


def parse_d3_source_spec(text: str, authority: str) -> list[AuthorityTask]:
    tasks: list[AuthorityTask] = []
    for chunk in re.split(r"(?=^### )", text, flags=re.MULTILINE):
        m = re.match(r"^###\s+(D3-\d{2})(?:…(D3-\d{2}))?\s*[—-]\s*(.+)$", chunk, re.MULTILINE)
        if not m:
            continue
        start = int(m.group(1).split("-")[1])
        end = int(m.group(2).split("-")[1]) if m.group(2) else start
        title = m.group(3).strip()
        body = chunk.split("\n", 1)[1].strip() if "\n" in chunk else title
        for n in range(start, end + 1):
            tid = f"D3-{n:02d}"
            tasks.append(AuthorityTask(tid, authority, f"{title} ({tid})", body[:400], "Day3"))
    return tasks


def parse_d3_rework(text: str, authority: str) -> list[AuthorityTask]:
    out: list[AuthorityTask] = []
    for line in text.splitlines():
        m = re.search(r"\*\*(D3-R\d{2})\s*[—-]\s*([^*]+)\*\*", line)
        if m:
            out.append(
                AuthorityTask(
                    m.group(1),
                    authority,
                    m.group(2).strip(),
                    f"Rework closure evidence in {authority}",
                    "Day3",
                )
            )
    for rid, title in [
        ("D3-R11", "Legacy revision evidence migration"),
        ("D3-R12", "Legacy tenant-source ownership compatibility"),
    ]:
        if not any(t.task_id == rid for t in out):
            out.append(
                AuthorityTask(
                    rid,
                    "docs/execution/D03-FINAL-COMPATIBILITY-CLOSURE.md",
                    title,
                    f"Compatibility closure in D03-FINAL-COMPATIBILITY-CLOSURE.md",
                    "Day3",
                )
            )
    return out


def parse_d7_pic(text: str, authority: str) -> list[AuthorityTask]:
    tasks: list[AuthorityTask] = []
    for chunk in re.split(r"(?=^### )", text, flags=re.MULTILINE):
        m = re.match(r"^###\s+(D7-PIC-\d{2})\s*[—-]\s*(.+)$", chunk, re.MULTILINE)
        if not m:
            continue
        tid, title = m.group(1), m.group(2).strip()
        body = chunk.split("\n", 1)[1].strip() if "\n" in chunk else ""
        acc = body.split("\n\n")[0][:500] if body else title
        tasks.append(AuthorityTask(tid, authority, title, acc, "Day7"))
    return tasks