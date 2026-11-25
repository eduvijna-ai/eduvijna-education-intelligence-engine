#!/usr/bin/env python3
"""C00 audit-only: authoritative requirements ledger + scope-map implementation evidence."""

from __future__ import annotations

import csv
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from c00_authority_parsers import (
    AuthorityTask,
    parse_checkbox_requirements,
    parse_d3_rework,
    parse_d3_source_spec,
    parse_d7_pic,
    parse_heading_tasks,
    parse_line_title_tasks,
    parse_pipe_authoritative_table,
)

REPO = Path(__file__).resolve().parents[2]
EXEC = REPO / "docs" / "execution"
FROZEN_BASELINE = "8b71aa03bcff21f021f43ea430935edf14070f68"
HELD_D11 = "d0f0745f6573bba0cfa93fa8eb0674cdd3b689d2"
HELD_D15 = "b69f97bf9ee1cb08e16121f301dc20e5e5645f6f"
HELD_D17 = "87df6a54ea8ad1c06157f894b4a4c4a1bfa3bbc1"

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

C00_CANDIDATE_CI = "45542731473"
C00_CANDIDATE_CI_RESULT = "SUCCESS_backend_frontend_compose_skipped"

DAY_HISTORY = {
    "Day1": ("", "PR #2", "36876757032", "FOUNDER_REVIEW", "FOUNDER_REVIEW"),
    "Day2": ("", "PR merged Day2", "NOT_VERIFIED", "HISTORICAL_ACCEPTED", "NOT_VERIFIED"),
    "Day3": ("", "COMPLETE", "NOT_VERIFIED", "HISTORICAL_ACCEPTED", "NOT_VERIFIED"),
    "Day4": ("", "PR Day4", "42783645367", "HISTORICAL_ACCEPTED", "SOURCE_PENDING"),
    "Day5": ("5d3927b5e582b2c5aa898b5e755bfbb194eca74b", "PR Day5", "NOT_VERIFIED", "HISTORICAL_ACCEPTED", "NOT_VERIFIED"),
    "Day6": ("dffd31b6da5558234ae0636fe4384305f4778400", "PR #20", "38246297963", "HISTORICAL_ACCEPTED", "NOT_VERIFIED"),
    "Day7": ("5b07830caafad4916e950da6293f8c039131a25d", "PR #23", "38671063433", "HISTORICAL_ACCEPTED", "NOT_VERIFIED"),
    "Day8": ("f8b422881632d39e32417650a47b32b6ee002e87", "PR #25", "38702017286", "HISTORICAL_ACCEPTED", "NOT_VERIFIED"),
    "Day9": ("e1608dd60eb0604b2d68d307e2a7e90db4afbbec", "PR #27", "39248106313", "HISTORICAL_ACCEPTED", "NOT_VERIFIED"),
    "Day10": ("4989994d7dbda1c2645bb79365544365fa20df4e", "PR #29", "42780248311", "HISTORICAL_ACCEPTED", "NOT_VERIFIED"),
    "Day11": (HELD_D11, "PR #31 held", "43038569379", "PARTIAL", "NOT_VERIFIED"),
    "Day12": ("afe2428be9f400c0af23da06b76070be28b04af2", "PR #34", "44882068512", "FOUNDER_MILESTONE_ONLY", "PARTIAL"),
    "Day13": ("efd269c7d73051777b53d912baefafbe1ba0ce96", "PR #53", "45386071086", "FOUNDER_MILESTONE_ONLY", "PARTIAL"),
    "Day14": ("3ecee26d367707152ca9b953ce15032c837f3ceb", "PR #55", "45393540240", "FOUNDER_MILESTONE_ONLY", "PARTIAL"),
    "Day15": (HELD_D15, "PR #57 held", "45409912353", "BLOCKED", "NOT_VERIFIED"),
    "Day16": ("39be6868462e557393fcf2dae25fec730ffe99f7", "PR #59", "45419005459", "FOUNDER_MILESTONE_ONLY", "PARTIAL"),
    "Day17": (HELD_D17, "PR #61 held", "45535514058", "BLOCKED", "NOT_VERIFIED"),
    "Day18": ("66291abdeaa30b2355f9a18cb92e199c0d17992f", "PR #63", "45539171598", "FOUNDER_MILESTONE_ONLY", "PARTIAL"),
}


@dataclass
class TaskRow:
    task_id: str
    day: str
    original_authority: str
    original_requirement: str
    acceptance_criterion: str = "NOT_VERIFIED: reconcile against original authority acceptance text"
    parent_task_id: str = ""
    approved_amendments: str = ""
    baseline_code_path: str = "NOT_VERIFIED: path not resolved at frozen baseline"
    test_path: str = "NOT_VERIFIED: test ID not resolved"
    historical_candidate_sha: str = "NOT_VERIFIED"
    historical_pr: str = "NOT_VERIFIED"
    historical_ci_result: str = "NOT_VERIFIED"
    current_baseline_evidence: str = "NOT_VERIFIED: merged baseline static inspection not executed this audit"
    external_evidence: str = ""
    engineering_acceptance_state: str = "NOT_VERIFIED"
    current_static_inspection_state: str = "NOT_RUN"
    current_test_execution_state: str = "NOT_RUN"
    technical_acceptance_state: str = "NOT_VERIFIED"
    residual_finding_ids: str = ""
    dependencies: str = "NOT_VERIFIED"
    closure_workstream: str = ""
    acceptance_proof: str = "Proposed: independent exact-HEAD review + stated acceptance criteria"
    owner: str = "Founder"
    historical_scope_state: str = ""


def git_show(ref: str, path: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "show", f"{ref}:{path}"],
            cwd=REPO,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except subprocess.CalledProcessError:
        return None


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def split_table_row(line: str) -> list[str] | None:
    s = line.strip()
    if not s.startswith("|") or s.count("|") < 2:
        return None
    parts = [p.strip() for p in s.strip("|").split("|")]
    if not parts or all(set(p) <= set("-:") for p in parts):
        return None
    head = parts[0].strip("*")
    if head in {"---", "Task", "ID", "Rework", ""}:
        return None
    return parts


def parse_scope_evidence(text: str, id_prefix: str) -> dict[str, dict[str, str]]:
    """Scope maps: implementation evidence only (not requirements authority)."""
    out: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        parts = split_table_row(line)
        if not parts or len(parts) < 3:
            continue
        tid = parts[0].strip("*")
        if not tid.startswith(id_prefix):
            continue
        state = parts[3].strip() if len(parts) > 3 else ""
        out[tid] = {
            "impl_ref": parts[2] if len(parts) > 2 else "",
            "historical_scope_state": state,
            "blocker": parts[4] if len(parts) > 4 else "",
            "scope_summary": parts[1] if len(parts) > 1 else "",
        }
    return out


def parse_scope_evidence_3col(text: str, id_prefix: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        parts = split_table_row(line)
        if not parts or len(parts) < 2:
            continue
        tid = parts[0].strip("*")
        if not tid.startswith(id_prefix):
            continue
        out[tid] = {
            "impl_ref": parts[1],
            "test_ref": parts[2] if len(parts) > 2 else "",
            "historical_scope_state": "",
            "blocker": "",
            "scope_summary": parts[1],
        }
    return out


def authority_from_task(t: AuthorityTask) -> TaskRow:
    return TaskRow(
        task_id=t.task_id,
        day=t.day,
        original_authority=t.original_authority,
        original_requirement=t.requirement,
        acceptance_criterion=t.acceptance,
    )


def closure_workstream(task_id: str) -> str:
    explicit = {
        "D5-DS01": "C02",
        "D14-R3-01": "C09",
        "D14-R3-02": "C09",
        "D14-R3-03": "C09",
        "D14-R3-04": "C09",
        "D14-R3-05": "C09",
        "D14-R3-06": "C09",
        "D15-R3-01": "C10",
        "D15-R3-02": "C10",
        "D15-R3-03": "C10",
        "D15-R3-04": "C10",
        "D15-R3-05": "C10",
        "D15-R3-06": "C10",
        "F03-A": "C08",
        "F03-B": "C08",
        "F04-A": "C08",
        "D13-31A": "C08",
        "D16-F01": "C11",
        "D16-F02": "C11",
        "D16-F03": "C11",
        "D17-F01": "C12",
        "D17-F02": "C13",
        "D17-F03": "C13",
        "D17-F04": "C13",
        "D17-F05": "C12",
        "D17-F06": "C12",
        "D17-F07": "C12",
        "D18-F01": "C14",
        "D18-F02": "C14",
        "D18-F03": "C14",
        "D18-F04": "C14",
        "D18-F05": "C14",
        "D18-F06": "C14",
        "D12-CORE-35": "C07",
    }
    if task_id in explicit:
        return explicit[task_id]
    if task_id.startswith("D3-R") or task_id.startswith("D1-") or task_id.startswith("D2-"):
        return "C01"
    if task_id.startswith("D3-"):
        return "C02"
    if task_id.startswith("D4-"):
        return "C03"
    if task_id.startswith("D5-"):
        return "C03"
    if task_id.startswith("D6-") or task_id.startswith("D7-") or task_id.startswith("D6-A"):
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
    return "C15"


def enrich_scope(row: TaskRow, ev: dict[str, str], scope_authority: str) -> None:
    row.current_baseline_evidence = (
        f"scope_map@{scope_authority}; historical_state={ev.get('historical_scope_state') or 'NOT_RECORDED'}"
    )
    row.historical_scope_state = ev.get("historical_scope_state", "")
    ref = ev.get("impl_ref") or ""
    if ref.startswith("`") or "/" in ref or ref.endswith(".py"):
        row.baseline_code_path = ref.strip("`")[:200]
    test = ev.get("test_ref") or ""
    if test:
        row.test_path = test.strip("`")[:200]


def apply_day_history(row: TaskRow) -> None:
    meta = DAY_HISTORY.get(row.day)
    if not meta:
        return
    sha, pr, ci, eng, tech_default = meta
    if sha:
        row.historical_candidate_sha = sha
    row.historical_pr = pr
    row.historical_ci_result = ci
    row.engineering_acceptance_state = eng
    if row.task_id.startswith("D11-") and row.historical_scope_state == "PASS":
        row.engineering_acceptance_state = "HISTORICAL_ACCEPTED"
        row.technical_acceptance_state = "NOT_VERIFIED"
    elif row.historical_scope_state:
        hs = row.historical_scope_state.upper()
        row.engineering_acceptance_state = (
            "HISTORICAL_ACCEPTED" if hs == "PASS" else f"HISTORICAL_SCOPE_{hs}"
        )
        row.technical_acceptance_state = tech_default if hs != "PASS" else "NOT_VERIFIED"
    else:
        row.technical_acceptance_state = tech_default
    row.current_test_execution_state = "NOT_RUN"
    row.current_static_inspection_state = "NOT_RUN"
    if row.day in {"Day11", "Day15", "Day17"}:
        row.external_evidence = "HELD_UNMERGED: code not on develop@8b71aa03"
    elif row.day in {"Day12", "Day13", "Day14", "Day16", "Day18"}:
        row.external_evidence = "FOUNDER_MILESTONE_ONLY: merged with deferred acceptance"


def finalize_row(row: TaskRow) -> None:
    row.closure_workstream = closure_workstream(row.task_id)
    apply_day_history(row)
    if row.task_id == "D5-DS01":
        row.engineering_acceptance_state = "DEFERRED"
        row.technical_acceptance_state = "SOURCE_PENDING"
        row.external_evidence = "Issue #16; Founder deferred authoritative Telangana packages"
    for field in ("historical_pr", "historical_ci_result", "closure_workstream", "owner"):
        if not getattr(row, field):
            setattr(row, field, "NOT_VERIFIED" if field != "owner" else "Founder")


def parse_dod(path: Path, prefix: str, day: str, authority: str) -> list[TaskRow]:
    text = read_text(path)
    in_dod = False
    rows: list[TaskRow] = []
    for line in text.splitlines():
        if line.strip().startswith("## Definition of Done"):
            in_dod = True
            continue
        if in_dod and line.startswith("## "):
            break
        if in_dod:
            m = re.match(r"^- \[ \] (.+)$", line.strip())
            if m:
                i = len(rows) + 1
                item = m.group(1).rstrip(";")
                rows.append(
                    TaskRow(
                        task_id=f"{prefix}-DOD-{i:02d}",
                        day=day,
                        original_authority=f"{authority}#definition-of-done (locally assigned DOD id; not original 36-grid)",
                        original_requirement=item,
                        acceptance_criterion=item,
                    )
                )
    return rows


def collect_authoritative() -> dict[str, TaskRow]:
    rows: dict[str, TaskRow] = {}

    def put(auth: AuthorityTask, parent: str = "") -> None:
        r = authority_from_task(auth)
        r.parent_task_id = parent
        rows[r.task_id] = r

    for r in parse_dod(EXEC / "D01-FOUNDATION.md", "D1", "Day1", "docs/execution/D01-FOUNDATION.md"):
        rows[r.task_id] = r
    for r in parse_dod(EXEC / "D02-CANONICAL-DOMAIN-MODEL.md", "D2", "Day2", "docs/execution/D02-CANONICAL-DOMAIN-MODEL.md"):
        rows[r.task_id] = r

    d3auth = "docs/execution/D03-SOURCE-INTELLIGENCE.md"
    for t in parse_d3_source_spec(read_text(EXEC / "D03-SOURCE-INTELLIGENCE.md"), d3auth):
        put(t)
    for t in parse_d3_rework(read_text(EXEC / "D03-REWORK-CLOSURE.md"), "docs/execution/D03-REWORK-CLOSURE.md"):
        put(t, parent="D3-34")

    d4auth = "docs/execution/D04-NCF-NCERT-CBSE.md"
    for t in parse_checkbox_requirements(read_text(EXEC / "D04-NCF-NCERT-CBSE.md"), re.compile(r"D4-\d{2}"), d4auth, "Day4"):
        put(t)

    d5auth = "docs/execution/D05-TELANGANA-CURRICULA.md"
    for t in parse_line_title_tasks(read_text(EXEC / "D05-TELANGANA-CURRICULA.md"), d5auth, "Day5"):
        put(t)
    put(
        AuthorityTask(
            "D5-DS01",
            "docs/execution/D05-DS01-TELANGANA-AUTHORITATIVE-SOURCES.md#issue-16",
            "Five deferred Telangana authoritative evidence packages",
            "Completion gate in D05-DS01-TELANGANA-AUTHORITATIVE-SOURCES.md",
            "Day5",
        )
    )

    day_specs = {
        6: "D06-EDUCATION-INTELLIGENCE-VALIDATORS.md",
        7: "D07-KNOWLEDGE-INTELLIGENCE-ANYTHINGLLM.md",
        8: "D08-LANGGRAPH-ORCHESTRATION.md",
        9: "D09-DIAGNOSTIC-DISTRACTOR-INTELLIGENCE.md",
        10: "D10-PREREQUISITES-ROOT-CAUSE-DIAGNOSTICS.md",
    }
    for num, fname in day_specs.items():
        prefix = f"D{num}"
        pat = re.compile(rf"{prefix}-\d{{2}}")
        spec_path = EXEC / fname
        auth = str(spec_path.relative_to(REPO))
        for t in parse_heading_tasks(read_text(spec_path), pat, auth, f"Day{num}"):
            put(t)

    for t in parse_d7_pic(read_text(EXEC / "D07-PRODUCTION-IDENTITY-CLOSURE.md"), "docs/execution/D07-PRODUCTION-IDENTITY-CLOSURE.md"):
        put(t, parent="D7-36")

    d11_spec = git_show(HELD_D11, "docs/execution/D11-JEE-MAIN-EXAM-INTELLIGENCE.md") or ""
    d11auth = f"git show {HELD_D11}:docs/execution/D11-JEE-MAIN-EXAM-INTELLIGENCE.md; GitHub issue #30"
    for t in parse_pipe_authoritative_table(d11_spec, "D11", d11auth, "Day11"):
        put(t)

    amendments = [
        ("D12-CORE-35", "", "Day12", "docs/execution/D12-SCOPE-MAP.md; issue #35", "JEE Advanced source intake CORE", "Issue #35 source intake obligations"),
        ("F03-A", "D13-12", "Day13", "docs/execution/D13-CLOSEOUT-EVIDENCE.md", "F03-A exact-count practice persistence", "STOPPED workstream"),
        ("F03-B", "D13-23", "Day13", "docs/execution/D13-CLOSEOUT-EVIDENCE.md", "F03-B CUET/CLAT practice", "STOPPED workstream"),
        ("F04-A", "D13-23", "Day13", "docs/execution/D13-CLOSEOUT-EVIDENCE.md", "F04-A CLAT current affairs", "STOPPED workstream"),
        ("D13-31A", "D13-31", "Day13", "docs/execution/D13-CLOSEOUT-EVIDENCE.md", "D13-31A replay durability", "Amendment"),
        ("D14-R3-01", "D14-30", "Day14", "docs/execution/D14-SCOPE-MAP.md; PR #55 review", "Canonical issuance persistence", "RES-R3-01"),
        ("D14-R3-02", "D14-02", "Day14", "docs/execution/D14-SCOPE-MAP.md", "Source trust curator flags", "RES-R3-02"),
        ("D14-R3-03", "D14-09", "Day14", "docs/execution/D14-SCOPE-MAP.md", "Academic validation disabled", "RES-R3-03"),
        ("D14-R3-04", "D14-04", "Day14", "docs/execution/D14-SCOPE-MAP.md", "Scope/planner gates", "RES-R3-04"),
        ("D14-R3-05", "D14-16", "Day14", "docs/execution/D14-SCOPE-MAP.md", "Bilingual equivalence", "RES-R3-05"),
        ("D14-R3-06", "D14-04", "Day14", "docs/execution/D14-SCOPE-MAP.md", "Extensibility bridges", "RES-R3-06"),
        ("D15-R3-01", "D15-10", "Day15", "execution-state.yml; issue #56 PR #57 review 7133926987", "ORM implicit attribute loads", "RES-D15-R3-01"),
        ("D15-R3-02", "D15-20", "Day15", "execution-state.yml", "Safety/transaction evidence", "RES-D15-R3-02"),
        ("D15-R3-03", "D15-15", "Day15", "execution-state.yml", "Stale scope descriptions", "RES-D15-R3-03"),
        ("D15-R3-04", "D15-25", "Day15", "execution-state.yml", "Trusted runtime boundary", "RES-D15-R3-04"),
        ("D15-R3-05", "D15-30", "Day15", "execution-state.yml", "Concurrency/idempotency", "RES-D15-R3-05"),
        ("D15-R3-06", "D15-36", "Day15", "execution-state.yml", "Founder signoff pending", "RES-D15-R3-06"),
    ]
    for tid, parent, day, auth, req, acc in amendments:
        r = TaskRow(tid, day, auth, req, acc, parent_task_id=parent, approved_amendments=tid)
        r.residual_finding_ids = tid if "R3" in tid or tid.startswith("F") or tid.endswith("A") else ""
        rows[tid] = r

    for tid, parent, day, auth, req in [
        ("D16-F01", "D16-36", "Day16", "execution-state.yml day16; issue #58", "Nested DTO/helper trust validation"),
        ("D16-F02", "D16-36", "Day16", "execution-state.yml day16", "Contradictory evidence fail-closed"),
        ("D16-F03", "D16-36", "Day16", "execution-state.yml day16", "Complete catalogue/policy fingerprint"),
        ("D17-F01", "D17-36", "Day17", "execution-state.yml day17; issue #60", "Direct principal trust"),
        ("D17-F02", "D17-36", "Day17", "execution-state.yml day17", "MCP auth/tools boundary"),
        ("D17-F03", "D17-36", "Day17", "execution-state.yml day17", "Synthetic job boundary"),
        ("D17-F04", "D17-36", "Day17", "execution-state.yml day17", "Lease expiry"),
        ("D17-F05", "D17-36", "Day17", "execution-state.yml day17", "Durable denied audit"),
        ("D17-F06", "D17-36", "Day17", "execution-state.yml day17", "Regression/migration/concurrency"),
        ("D17-F07", "D17-36", "Day17", "execution-state.yml day17", "Failed CI257 ruff"),
        ("D18-F01", "D18-36", "Day18", "execution-state.yml day18; issue #62", "Other-origin network detection"),
        ("D18-F02", "D18-36", "Day18", "execution-state.yml day18", "Missing/empty bundle acceptance"),
        ("D18-F03", "D18-36", "Day18", "execution-state.yml day18", "Structural fixture contracts"),
        ("D18-F04", "D18-36", "Day18", "execution-state.yml day18", "Hierarchy/STEM/integration"),
        ("D18-F05", "D18-36", "Day18", "execution-state.yml day18", "Accessibility/responsive/adversarial"),
        ("D18-F06", "D18-36", "Day18", "execution-state.yml day18", "Actual authenticated workflows"),
    ]:
        r = TaskRow(tid, day, auth, req, "Independent review finding; see PR reviews", parent_task_id=parent, approved_amendments=tid)
        r.residual_finding_ids = tid
        rows[tid] = r

  # Days 11-18 scope evidence merge
    scope_sources: list[tuple[str, str, str, bool]] = [
        ("D6", "docs/execution/D06-SCOPE-MAP.md", "Day6", False),
        ("D7", "docs/execution/D07-SCOPE-MAP.md", "Day7", False),
        ("D8", "docs/execution/D08-SCOPE-MAP.md", "Day8", False),
        ("D9", "docs/execution/D09-SCOPE-MAP.md", "Day9", False),
        ("D10", "docs/execution/D10-SCOPE-MAP.md", "Day10", False),
        ("D11", f"git show {HELD_D11}:docs/execution/D11-SCOPE-MAP.md", "Day11", True),
        ("D12", "docs/execution/D12-SCOPE-MAP.md", "Day12", True),
        ("D13", "docs/execution/D13-SCOPE-MAP.md", "Day13", True),
        ("D14", "docs/execution/D14-SCOPE-MAP.md", "Day14", True),
        ("D15", f"git show {HELD_D15}:docs/execution/D15-SCOPE-MAP.md", "Day15", True),
        ("D16", "docs/execution/D16-SCOPE-MAP.md", "Day16", True),
        ("D17", f"git show {HELD_D17}:docs/execution/D17-SCOPE-MAP.md", "Day17", True),
        ("D18", "docs/execution/D18-SCOPE-MAP.md", "Day18", True),
    ]
    for prefix, loc, day, five_col in scope_sources:
        if loc.startswith("git show"):
            ref, path = loc.split(":", 1)
            ref = ref.replace("git show ", "")
            text = git_show(ref, path) or ""
        else:
            text = read_text(REPO / loc)
        evmap = parse_scope_evidence(text, f"{prefix}-") if five_col else parse_scope_evidence_3col(text, f"{prefix}-")
        for tid, ev in evmap.items():
            if tid not in rows:
                rows[tid] = TaskRow(
                    tid,
                    day,
                    f"MISSING_SPEC: {tid} not in authoritative spec extracted this candidate",
                    ev.get("scope_summary", "UNKNOWN"),
                    "NOT_VERIFIED: no authoritative requirement located",
                )
            enrich_scope(rows[tid], ev, loc)

    issue_authority = {
        "Day12": "GitHub issue #33 approved tasklist",
        "Day13": "GitHub issue #52 approved tasklist",
        "Day14": "GitHub issue #54 approved tasklist",
        "Day15": f"git show {HELD_D15}:docs/execution/D15-SCOPE-MAP.md; issue #56",
        "Day16": "GitHub issue #58 approved tasklist",
        "Day17": f"git show {HELD_D17}:docs/execution/D17-SCOPE-MAP.md; issue #60",
        "Day18": "GitHub issue #62 approved tasklist",
    }
    for tid, row in list(rows.items()):
        if tid.startswith(("D12-", "D13-", "D14-", "D15-", "D16-", "D17-", "D18-")) and "MISSING_SPEC" in row.original_authority:
            day = row.day
            if day in issue_authority:
                row.original_authority = issue_authority[day]

    for r in rows.values():
        finalize_row(r)
    return rows


def to_csv_dict(row: TaskRow) -> dict[str, str]:
    d = {k: getattr(row, k, "") for k in CSV_COLUMNS}
    return d


def main() -> None:
    rows = sorted(collect_authoritative().values(), key=lambda r: r.task_id)
    out = EXEC / "C00-MASTER-TASK-EVIDENCE.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for row in rows:
            w.writerow(to_csv_dict(row))
    print(f"Wrote {len(rows)} rows to {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()