#!/usr/bin/env python3
"""C00 audit-only: build master task evidence CSV and companion indexes from repo specs."""

from __future__ import annotations

import csv
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXEC = REPO / "docs" / "execution"
FROZEN_BASELINE = "8b71aa03bcff21f021f43ea430935edf14070f68"
GOVERNANCE_SEED = "03fcd784b6a3940f04c1879a269a9987f87f677e"

CSV_COLUMNS = [
    "task_id",
    "parent_task_id",
    "day",
    "original_authority",
    "original_requirement",
    "acceptance_criterion",
    "approved_amendments",
    "baseline_code_path",
    "test_path",
    "historical_candidate_sha",
    "historical_pr",
    "historical_ci_result",
    "current_baseline_evidence",
    "external_evidence",
    "engineering_acceptance_state",
    "current_static_inspection_state",
    "current_test_execution_state",
    "technical_acceptance_state",
    "residual_finding_ids",
    "dependencies",
    "closure_workstream",
    "acceptance_proof",
    "owner",
]

STATE_VOCAB = {
    "PASS",
    "PARTIAL",
    "BLOCKED",
    "SOURCE_PENDING",
    "NOT_STARTED",
    "UNKNOWN",
    "NOT_VERIFIED",
    "HISTORICAL_ACCEPTED",
    "FOUNDER_MILESTONE_ONLY",
    "DEFERRED",
    "MISSING_SPEC",
}


@dataclass
class TaskRow:
    task_id: str
    day: str
    original_authority: str
    original_requirement: str
    acceptance_criterion: str = ""
    parent_task_id: str = ""
    approved_amendments: str = ""
    baseline_code_path: str = "UNKNOWN"
    test_path: str = "UNKNOWN"
    historical_candidate_sha: str = "UNKNOWN"
    historical_pr: str = ""
    historical_ci_result: str = "NOT_VERIFIED"
    current_baseline_evidence: str = "NOT_VERIFIED"
    external_evidence: str = ""
    engineering_acceptance_state: str = "UNKNOWN"
    current_static_inspection_state: str = "NOT_VERIFIED"
    current_test_execution_state: str = "NOT_RUN"
    technical_acceptance_state: str = "NOT_VERIFIED"
    residual_finding_ids: str = ""
    dependencies: str = ""
    closure_workstream: str = "C15"
    acceptance_proof: str = ""
    owner: str = "Founder"
    scope_state: str = ""  # from scope map State column when present

    def to_csv(self) -> dict[str, str]:
        return {k: getattr(self, k) if k != "scope_state" else "" for k in CSV_COLUMNS}


def git_show(ref: str, path: str) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "show", f"{ref}:{path}"],
            cwd=REPO,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out
    except subprocess.CalledProcessError:
        return None


def read_text(path: Path) -> str:
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace")
    return ""


def split_table_row(line: str) -> list[str] | None:
    s = line.strip()
    if not s.startswith("|") or s.count("|") < 2:
        return None
    parts = [p.strip() for p in s.strip("|").split("|")]
    if not parts:
        return None
    head = parts[0].strip("*").strip()
    if head in {"---", "Task", "ID", "Rework", ""}:
        return None
    if all(set(p) <= set("-:") for p in parts):
        return None
    return parts


def parse_scope_table(text: str, id_prefix: str) -> list[TaskRow]:
    """5-column scope maps: ID | task | evidence | State | blocker."""
    rows: list[TaskRow] = []
    day = "Day" + id_prefix[1:id_prefix.index("-")]
    for line in text.splitlines():
        parts = split_table_row(line)
        if not parts or len(parts) < 4:
            continue
        tid = parts[0].strip("*")
        if not tid.startswith(id_prefix):
            continue
        rows.append(
            TaskRow(
                task_id=tid,
                day=day,
                original_authority=f"docs/execution scope matrix; frozen baseline {FROZEN_BASELINE}",
                original_requirement=parts[1],
                baseline_code_path=parts[2] if len(parts) > 2 else "UNKNOWN",
                scope_state=parts[3] if len(parts) > 3 else "",
                acceptance_criterion=parts[4] if len(parts) > 4 else "",
                current_static_inspection_state="PARTIAL"
                if len(parts) > 3 and parts[3].strip() == "PARTIAL"
                else "NOT_VERIFIED",
            )
        )
    return rows


def parse_delivery_table(text: str, id_pattern: re.Pattern[str], day: str, authority: str) -> list[TaskRow]:
    rows: list[TaskRow] = []
    for line in text.splitlines():
        parts = split_table_row(line)
        if not parts or len(parts) < 2:
            continue
        tid = parts[0].strip("*")
        if not id_pattern.match(tid):
            continue
        rows.append(
            TaskRow(
                task_id=tid,
                day=day,
                original_authority=authority,
                original_requirement=parts[1],
                current_baseline_evidence=parts[2] if len(parts) > 2 else "UNKNOWN",
                baseline_code_path=parts[1] if len(parts) == 2 else (parts[2] if len(parts) > 2 else "UNKNOWN"),
                acceptance_criterion=parts[-1],
            )
        )
    return rows


def parse_task_implementation_table(
    text: str, id_pattern: re.Pattern[str], day: str, authority: str
) -> list[TaskRow]:
    """3-column Day6-style: Task | Implementation | Tests."""
    rows: list[TaskRow] = []
    for line in text.splitlines():
        parts = split_table_row(line)
        if not parts or len(parts) < 2:
            continue
        tid = parts[0].strip("*")
        if not id_pattern.match(tid):
            continue
        rows.append(
            TaskRow(
                task_id=tid,
                day=day,
                original_authority=authority,
                original_requirement=parts[1],
                baseline_code_path=parts[1],
                test_path=parts[2] if len(parts) > 2 else "UNKNOWN",
            )
        )
    return rows


def parse_dod_checklist(path: Path, prefix: str, day: str, authority: str) -> list[TaskRow]:
    text = read_text(path)
    in_dod = False
    items: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith("## Definition of Done"):
            in_dod = True
            continue
        if in_dod and line.startswith("## "):
            break
        if in_dod:
            m = re.match(r"^- \[ \] (.+)$", line.strip())
            if m:
                items.append(m.group(1).rstrip(";"))
    rows: list[TaskRow] = []
    for i, item in enumerate(items, 1):
        rows.append(
            TaskRow(
                task_id=f"{prefix}-DOD-{i:02d}",
                day=day,
                original_authority=authority,
                original_requirement=item,
                acceptance_criterion=item,
                closure_workstream="C01",
            )
        )
    return rows


def workstream_for_task(task_id: str) -> str:
    if task_id.startswith("D3-R") or task_id.startswith("D1-") or task_id.startswith("D2-"):
        return "C01"
    if task_id == "D5-DS01":
        return "C02"
    if task_id.startswith("D3-") or task_id.startswith("D4-"):
        return "C02"
    if task_id.startswith("D5-"):
        return "C03"
    if task_id.startswith("D6-") or task_id.startswith("D7-"):
        return "C04"
    if task_id.startswith("D8-") or task_id.startswith("D9-") or task_id.startswith("D10-"):
        return "C05"
    if task_id.startswith("D11-"):
        return "C06"
    if task_id.startswith("D12-"):
        return "C07"
    if task_id.startswith("D13-"):
        return "C08"
    if task_id.startswith("D14-"):
        return "C09"
    if task_id.startswith("D15-"):
        return "C10"
    if task_id.startswith("D16-"):
        return "C11"
    if task_id.startswith("D17-"):
        num = task_id.split("-")[1]
        if num.isdigit() and int(num) <= 14:
            return "C12"
        return "C13"
    if task_id.startswith("D18-"):
        return "C14"
    if task_id.startswith("D6-A"):
        return "C04"
    if task_id.startswith("D7-PIC"):
        return "C04"
    if task_id.startswith("D") and "-F" in task_id:
        d = task_id.split("-")[0]
        return {"D16": "C11", "D17": "C12", "D18": "C14"}.get(d, "C15")
    if task_id.startswith("F03") or task_id.startswith("F04") or task_id == "D13-31A":
        return "C08"
    if task_id.startswith("R3-"):
        return "C09"
    return "C15"


def apply_day_governance(row: TaskRow) -> None:
    ws = workstream_for_task(row.task_id)
    row.closure_workstream = ws
    st = row.scope_state.upper() if row.scope_state else ""
    if st in STATE_VOCAB:
        row.technical_acceptance_state = st
        row.engineering_acceptance_state = (
            "HISTORICAL_ACCEPTED" if st == "PASS" else "NOT_VERIFIED"
        )
    day_yaml_notes = {
        "Day1": ("FOUNDER_REVIEW", "PR #2 merged; founder_approval:false in YAML"),
        "Day2": ("HISTORICAL_ACCEPTED", "COMPLETE in YAML; founder_approval:false"),
        "Day3": ("HISTORICAL_ACCEPTED", "COMPLETE + D3-R01..12 closed"),
        "Day4": ("HISTORICAL_ACCEPTED", "COMPLETE; issue #12 official source CI FAILED"),
        "Day5": ("HISTORICAL_ACCEPTED", "founder_approval:true; D5-DS01 deferred #16"),
        "Day6": ("HISTORICAL_ACCEPTED", "founder_approval:true; engineering CI GREEN"),
        "Day7": ("HISTORICAL_ACCEPTED", "PR23 merged supersedes PR22"),
        "Day8": ("HISTORICAL_ACCEPTED", "PR25 merged"),
        "Day9": ("HISTORICAL_ACCEPTED", "PR27; UAT deferred"),
        "Day10": ("HISTORICAL_ACCEPTED", "PR29; postmerge Day4 CI failed"),
        "Day11": ("PARTIAL", "PR31 held d0f0745f; 13/22/1 ledger"),
        "Day12": ("FOUNDER_MILESTONE_ONLY", "PR34 merged; deferred ledger"),
        "Day13": ("FOUNDER_MILESTONE_ONLY", "PR53 merged; stopped workstreams"),
        "Day14": ("FOUNDER_MILESTONE_ONLY", "PR55 merged; R3-01..06"),
        "Day15": ("BLOCKED", "PR57 held b69f97bf unmerged"),
        "Day16": ("FOUNDER_MILESTONE_ONLY", "PR59 merged"),
        "Day17": ("BLOCKED", "PR61 held 87df6a54; CI257 FAILED_RUFF"),
        "Day18": ("FOUNDER_MILESTONE_ONLY", "PR63 merged; CI261 targeted only"),
    }
    if row.day in day_yaml_notes and not row.scope_state:
        eng, note = day_yaml_notes[row.day]
        row.engineering_acceptance_state = eng
        row.external_evidence = note


def collect_rows() -> list[TaskRow]:
    all_rows: dict[str, TaskRow] = {}

    def add(rows: list[TaskRow]) -> None:
        for r in rows:
            if r.task_id in all_rows:
                existing = all_rows[r.task_id]
                if not existing.original_requirement and r.original_requirement:
                    all_rows[r.task_id] = r
            else:
                all_rows[r.task_id] = r

    # Day 1–2 Definition-of-Done canonical rows (no Dxx-01..36 numbering in original spec)
    add(
        parse_dod_checklist(
            EXEC / "D01-FOUNDATION.md",
            "D1",
            "Day1",
            "docs/execution/D01-FOUNDATION.md#definition-of-done; GitHub PR #2",
        )
    )
    add(
        parse_dod_checklist(
            EXEC / "D02-CANONICAL-DOMAIN-MODEL.md",
            "D2",
            "Day2",
            "docs/execution/D02-CANONICAL-DOMAIN-MODEL.md#definition-of-done",
        )
    )

    # Day 3 core + rework
    d3 = parse_delivery_table(
        read_text(EXEC / "D03-COMPLETION-REPORT.md"),
        re.compile(r"D3-\d{2}$"),
        "Day3",
        "docs/execution/D03-COMPLETION-REPORT.md",
    )
    add(d3)
    d3r_text = read_text(EXEC / "D03-REWORK-CLOSURE.md")
    d3r_rows: list[TaskRow] = []
    for line in d3r_text.splitlines():
        m = re.search(r"\*\*(D3-R\d{2})\s*[—-]\s*([^*]+)\*\*", line)
        if not m:
            continue
        d3r_rows.append(
            TaskRow(
                task_id=m.group(1),
                parent_task_id="D3-36",
                day="Day3",
                original_authority="docs/execution/D03-REWORK-CLOSURE.md",
                original_requirement=m.group(2).strip(),
                engineering_acceptance_state="HISTORICAL_ACCEPTED",
            )
        )
    add(d3r_rows)
    for rid, title in [("D3-R11", "Legacy revision evidence migration"), ("D3-R12", "Legacy tenant-source ownership compatibility")]:
        add(
            [
                TaskRow(
                    task_id=rid,
                    parent_task_id="D3-36",
                    day="Day3",
                    original_authority="docs/execution/D03-FINAL-COMPATIBILITY-CLOSURE.md",
                    original_requirement=title,
                    engineering_acceptance_state="HISTORICAL_ACCEPTED",
                )
            ]
        )

    # Day 4–5 delivery evidence
    add(
        parse_delivery_table(
            read_text(EXEC / "D04-DELIVERY-EVIDENCE.md"),
            re.compile(r"D4-\d{2}$"),
            "Day4",
            "docs/execution/D04-DELIVERY-EVIDENCE.md; D04-NCF-NCERT-CBSE.md",
        )
    )
    add(
        parse_delivery_table(
            read_text(EXEC / "D05-DELIVERY-EVIDENCE.md"),
            re.compile(r"D5-\d{2}$"),
            "Day5",
            "docs/execution/D05-DELIVERY-EVIDENCE.md",
        )
    )
    add(
        [
            TaskRow(
                task_id="D5-DS01",
                day="Day5",
                original_authority="docs/execution/D05-DS01-TELANGANA-AUTHORITATIVE-SOURCES.md",
                original_requirement="Authoritative Telangana source ingestion (five packages)",
                acceptance_criterion="Issue #16; deferred by Founder",
                engineering_acceptance_state="DEFERRED",
                technical_acceptance_state="SOURCE_PENDING",
                closure_workstream="C02",
            )
        ]
    )

    # Day 6–10 scope maps (3-column Task | Location | Evidence)
    for day_num, prefix in [
        (6, "D6"),
        (7, "D7"),
        (8, "D8"),
        (9, "D9"),
        (10, "D10"),
    ]:
        path = EXEC / f"D{day_num:02d}-SCOPE-MAP.md"
        if path.is_file():
            add(
                parse_task_implementation_table(
                    read_text(path),
                    re.compile(rf"{prefix}-\d{{2}}$"),
                    f"Day{day_num}",
                    str(path.relative_to(REPO)),
                )
            )

    add(
        parse_delivery_table(
            read_text(EXEC / "D06-DELIVERY-EVIDENCE.md"),
            re.compile(r"D6-A\d{2}"),
            "Day6",
            "docs/execution/D06-DELIVERY-EVIDENCE.md",
        )
    )

    # Scope maps on governance branch / baseline tree (5-column evidence matrices)
    for day_num, prefix in [
        (12, "D12"),
        (13, "D13"),
        (14, "D14"),
        (16, "D16"),
        (18, "D18"),
    ]:
        path = EXEC / f"D{day_num:02d}-SCOPE-MAP.md"
        if path.is_file():
            add(parse_scope_table(read_text(path), f"{prefix}-"))

    # Held / unmerged scope maps via git ref
    d11_text = git_show("d0f0745f6573bba0cfa93fa8eb0674cdd3b689d2", "docs/execution/D11-SCOPE-MAP.md")
    if d11_text:
        add(parse_scope_table(d11_text, "D11-"))
    d15_text = git_show(
        "b69f97bf9ee1cb08e16121f301dc20e5e5645f6f", "docs/execution/D15-SCOPE-MAP.md"
    )
    if d15_text:
        add(parse_scope_table(d15_text, "D15-"))
    d17_text = git_show(
        "87df6a54ea8ad1c06157f894b4a4c4a1bfa3bbc1", "docs/execution/D17-SCOPE-MAP.md"
    )
    if d17_text:
        add(parse_scope_table(d17_text, "D17-"))

    # Residual / amendment rows (unique IDs, parent links)
    amendments = [
        ("D6-A01", "D6-36", "Day6", "Day 6 P1 closure amendment", "docs/execution/D06-FINAL-P1-CLOSURE.md"),
        *[
            (
                f"D7-PIC-{i:02d}",
                "D7-36",
                "Day7",
                f"Production identity closure slice {i}",
                "docs/execution/D07-PRODUCTION-IDENTITY-CLOSURE.md",
            )
            for i in range(1, 11)
        ],
        ("R3-01", "D14-36", "Day14", "Canonical issuance persistence disabled", "docs/execution/D14-SCOPE-MAP.md"),
        ("R3-02", "D14-36", "Day14", "Source trust / curator flags", "docs/execution/D14-SCOPE-MAP.md"),
        ("R3-03", "D14-36", "Day14", "Academic validation disabled", "docs/execution/D14-SCOPE-MAP.md"),
        ("R3-04", "D14-36", "Day14", "Scope/planner gates", "docs/execution/D14-SCOPE-MAP.md"),
        ("R3-05", "D14-36", "Day14", "Bilingual equivalence evidence", "docs/execution/D14-SCOPE-MAP.md"),
        ("R3-06", "D14-36", "Day14", "Extensibility/bridges NOT_READY", "docs/execution/D14-SCOPE-MAP.md"),
        ("F03-A", "D13-12", "Day13", "Stopped workstream F03-A", "D13-CLOSEOUT-EVIDENCE.md"),
        ("F03-B", "D13-23", "Day13", "Stopped workstream F03-B", "D13-CLOSEOUT-EVIDENCE.md"),
        ("F04-A", "D13-23", "Day13", "Stopped workstream F04-A", "D13-CLOSEOUT-EVIDENCE.md"),
        ("D13-31A", "D13-31", "Day13", "D13-31 replay durability amendment", "D13-CLOSEOUT-EVIDENCE.md"),
        ("D16-F01", "D16-36", "Day16", "Nested DTO/helper trust validation", "execution-state.yml day16 residual_findings"),
        ("D16-F02", "D16-36", "Day16", "Contradictory evidence fail-closed", "execution-state.yml day16 residual_findings"),
        ("D16-F03", "D16-36", "Day16", "Complete catalogue/policy fingerprint", "execution-state.yml day16 residual_findings"),
        ("D17-F01", "D17-36", "Day17", "Direct principal trust", "execution-state.yml day17 residual_findings"),
        ("D17-F02", "D17-36", "Day17", "MCP auth/tools boundary", "execution-state.yml day17 residual_findings"),
        ("D17-F03", "D17-36", "Day17", "Synthetic job boundary", "execution-state.yml day17 residual_findings"),
        ("D17-F04", "D17-36", "Day17", "Lease expiry", "execution-state.yml day17 residual_findings"),
        ("D17-F05", "D17-36", "Day17", "Durable denied audit", "execution-state.yml day17 residual_findings"),
        ("D17-F06", "D17-36", "Day17", "Regression/migration/concurrency", "execution-state.yml day17 residual_findings"),
        ("D17-F07", "D17-36", "Day17", "Failed CI257 ruff", "execution-state.yml day17 residual_findings"),
        ("D18-F01", "D18-36", "Day18", "Other-origin network detection", "execution-state.yml day18 residual_findings"),
        ("D18-F02", "D18-36", "Day18", "Missing/empty bundle acceptance", "execution-state.yml day18 residual_findings"),
        ("D18-F03", "D18-36", "Day18", "Structural fixture contracts", "execution-state.yml day18 residual_findings"),
        ("D18-F04", "D18-36", "Day18", "Hierarchy/STEM/integration", "execution-state.yml day18 residual_findings"),
        ("D18-F05", "D18-36", "Day18", "Accessibility/responsive/adversarial", "execution-state.yml day18 residual_findings"),
        ("D18-F06", "D18-36", "Day18", "Actual authenticated workflows", "execution-state.yml day18 residual_findings"),
    ]
    for tid, parent, day, req, auth in amendments:
        add(
            [
                TaskRow(
                    task_id=tid,
                    parent_task_id=parent,
                    day=day,
                    original_authority=auth,
                    original_requirement=req,
                    approved_amendments=tid,
                    technical_acceptance_state="NOT_VERIFIED",
                    engineering_acceptance_state="NOT_VERIFIED",
                )
            ]
        )

    for r in list(all_rows.values()):
        apply_day_governance(r)

    return sorted(all_rows.values(), key=lambda x: x.task_id)


def write_csv(rows: list[TaskRow], dest: Path) -> None:
    with dest.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for row in rows:
            w.writerow(row.to_csv())


def main() -> None:
    rows = collect_rows()
    out = EXEC / "C00-MASTER-TASK-EVIDENCE.csv"
    write_csv(rows, out)
    print(f"Wrote {len(rows)} rows to {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()