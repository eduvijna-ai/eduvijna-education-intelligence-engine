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
        if acceptance_from_body and body:
            acc = f"{authority}#section-{tid} — {body.strip()}"
        else:
            acc = title
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
            loc = f"{authority}#section-{tid}"
            tasks.append(
                AuthorityTask(
                    tid,
                    authority,
                    f"{title} ({tid})",
                    f"{loc} — {body.strip()}" if body.strip() else loc,
                    "Day3",
                )
            )
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
        acc = f"{authority}#section-{tid} — {body.strip()}" if body else title
        tasks.append(AuthorityTask(tid, authority, title, acc, "Day7"))
    return tasks


def parse_two_column_summary_table(
    text: str, id_prefix: str, authority: str, day: str
) -> list[AuthorityTask]:
    """| D6-01 | Summary | or | **D6-01** | Summary |"""
    tasks: list[AuthorityTask] = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 2:
            continue
        tid = parts[0].strip("*").strip()
        if not tid.startswith(id_prefix) or tid in {"ID", "---"}:
            continue
        if set(parts[0]) <= set("-:"):
            continue
        summary = parts[1]
        acc = f"{authority}#row-{tid} — {summary}"
        tasks.append(AuthorityTask(tid, authority, summary, acc, day))
    return tasks


def parse_three_column_task_table(
    text: str, id_prefix: str, authority: str, day: str
) -> list[AuthorityTask]:
    """| D10-01 | Task | Required acceptance |"""
    tasks: list[AuthorityTask] = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 3:
            continue
        tid = parts[0].strip("*").strip()
        if not tid.startswith(id_prefix) or tid in {"ID", "---"}:
            continue
        if set(parts[0]) <= set("-:"):
            continue
        req = parts[1]
        acc = parts[2] if len(parts) > 2 else req
        tasks.append(AuthorityTask(tid, authority, req, f"{authority}#row-{tid} — {acc}", day))
    return tasks


def parse_d6_amendments(text: str, authority: str) -> list[AuthorityTask]:
    """D6-A01..A12 from D06-DELIVERY-EVIDENCE acceptance-closure table."""
    expanded: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 2:
            continue
        rid = parts[0]
        if not rid.startswith("D6-A"):
            continue
        impl = parts[1]
        if "A04–A05" in rid or "A04-A05" in rid:
            expanded.append(("D6-A04", impl + " (split A04)"))
            expanded.append(("D6-A05", impl + " (split A05)"))
        elif "A07–A08" in rid or "A07-A08" in rid:
            expanded.append(("D6-A07", impl + " (split A07)"))
            expanded.append(("D6-A08", impl + " (split A08)"))
        elif "A10–A12" in rid or "A10-A12" in rid:
            expanded.append(("D6-A10", impl + " (split A10)"))
            expanded.append(("D6-A11", impl + " (split A11)"))
            expanded.append(("D6-A12", impl + " (split A12)"))
        else:
            expanded.append((rid, impl))
    out: list[AuthorityTask] = []
    for tid, impl in expanded:
        out.append(
            AuthorityTask(
                tid,
                authority,
                impl,
                f"{authority}#acceptance-closure-{tid} — {impl}",
                "Day6",
            )
        )
    return out


def parse_d12_core_workstream(text: str, authority: str) -> list[AuthorityTask]:
    """Issue #35 CORE-01..CORE-06 rows."""
    tasks: list[AuthorityTask] = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 3:
            continue
        label = parts[0].strip("*")
        m = re.match(r"CORE-(\d{2})", label)
        if not m:
            continue
        tid = f"D12-CORE-{m.group(1)}"
        req = parts[1]
        acc = parts[2] if len(parts) > 2 else req
        tasks.append(
            AuthorityTask(
                tid,
                authority,
                req,
                f"{authority}#row-{tid} — {acc}",
                "Day12",
            )
        )
    return tasks


def parse_github_authority_tables(
    body: str, id_prefix: str, authority: str, day: str
) -> list[AuthorityTask]:
    """Best-effort 3-column issue tables; falls back to 2-column."""
    three = parse_three_column_task_table(body, id_prefix, authority, day)
    if len(three) >= 12:
        return three
    return parse_two_column_summary_table(body, id_prefix, authority, day)