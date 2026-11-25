#!/usr/bin/env python3
"""C00 audit-only: authoritative requirements ledger + scope-map implementation evidence."""

from __future__ import annotations

import csv
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from c00_authority_parsers import (
    AuthorityTask,
    parse_checkbox_requirements,
    parse_d12_core_workstream,
    parse_d3_rework,
    parse_d3_source_spec,
    parse_d6_amendments,
    parse_d7_pic,
    parse_github_authority_tables,
    parse_heading_tasks,
    parse_line_title_tasks,
    parse_pipe_authoritative_table,
    parse_three_column_task_table,
    parse_two_column_summary_table,
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

C00_CANDIDATE_CI = "45543441778"
C00_CANDIDATE_CI_RESULT = "SUCCESS_backend_frontend; compose_skipped"
C00_PRIOR_CANDIDATE_CI = "45542731473:SUCCESS_backend_frontend;compose_skipped"

DAY_HISTORY = {
    "Day1": ("", "PR #2", "36876757032", "FOUNDER_REVIEW", "FOUNDER_REVIEW"),
    "Day2": ("", "PR merged Day2", "NOT_VERIFIED", "HISTORICAL_ACCEPTED", "NOT_VERIFIED"),
    "Day3": ("", "COMPLETE", "NOT_VERIFIED", "HISTORICAL_ACCEPTED", "NOT_VERIFIED"),
    "Day4": ("", "PR Day4", "42783645367:FAILED_INCOMPLETE_OFFICIAL_SOURCE_COVERAGE", "HISTORICAL_ACCEPTED", "NOT_VERIFIED"),
    "Day5": ("5d3927b5e582b2c5aa898b5e755bfbb194eca74b", "PR Day5", "NOT_VERIFIED:per-day CI not recorded", "HISTORICAL_ACCEPTED", "NOT_VERIFIED"),
    "Day6": (
        "682e4982ac46238e8efe3b32e50aa10c6b2dd519",
        "PR #20 correction candidate (merge dffd31b6)",
        "38246297963:GREEN_engineering",
        "HISTORICAL_ACCEPTED",
        "NOT_VERIFIED",
    ),
    "Day7": ("5b07830caafad4916e950da6293f8c039131a25d", "PR #23", "38671063433", "HISTORICAL_ACCEPTED", "NOT_VERIFIED"),
    "Day8": ("f8b422881632d39e32417650a47b32b6ee002e87", "PR #25", "38702017286", "HISTORICAL_ACCEPTED", "NOT_VERIFIED"),
    "Day9": ("e1608dd60eb0604b2d68d307e2a7e90db4afbbec", "PR #27", "39248106313", "HISTORICAL_ACCEPTED", "NOT_VERIFIED"),
    "Day10": (
        "4989994d7dbda1c2645bb79365544365fa20df4e",
        "PR #29",
        "42780248311:postmerge_official_source_CI_failed",
        "HISTORICAL_ACCEPTED",
        "NOT_VERIFIED",
    ),
    "Day11": (HELD_D11, "PR #31 held", "43038569379:NOT_VERIFIED_conclusion", "PARTIAL", "NOT_VERIFIED"),
    "Day12": ("afe2428be9f400c0af23da06b76070be28b04af2", "PR #34", "44882068512:NOT_VERIFIED_conclusion", "FOUNDER_MILESTONE_ONLY", "PARTIAL"),
    "Day13": ("efd269c7d73051777b53d912baefafbe1ba0ce96", "PR #53", "45386071086:NOT_VERIFIED_conclusion", "FOUNDER_MILESTONE_ONLY", "PARTIAL"),
    "Day14": ("3ecee26d367707152ca9b953ce15032c837f3ceb", "PR #55", "45393540240:NOT_VERIFIED_conclusion", "FOUNDER_MILESTONE_ONLY", "PARTIAL"),
    "Day15": (HELD_D15, "PR #57 held", "45409912353:SUCCESS_targeted_backend_compose_skipped", "BLOCKED", "NOT_VERIFIED"),
    "Day16": ("39be6868462e557393fcf2dae25fec730ffe99f7", "PR #59", "45419005459:NOT_VERIFIED_conclusion", "FOUNDER_MILESTONE_ONLY", "PARTIAL"),
    "Day17": (HELD_D17, "PR #61 held", "45535514058:FAILED", "BLOCKED", "NOT_VERIFIED"),
    "Day18": (
        "66291abdeaa30b2355f9a18cb92e199c0d17992f",
        "PR #63",
        "45539171598:targeted_14_browser_compose_skipped",
        "FOUNDER_MILESTONE_ONLY",
        "PARTIAL",
    ),
}

GITHUB_ISSUE_MAP = {
    33: ("D12", "Day12"),
    52: ("D13", "Day13"),
    54: ("D14", "Day14"),
    56: ("D15", "Day15"),
    58: ("D16", "Day16"),
    60: ("D17", "Day17"),
    62: ("D18", "Day18"),
}

RESIDUAL_BY_TASK: dict[str, str] = {
    "D5-DS01": "RES-SRC-016",
    "D4-12": "RES-SRC-012",
    "D11-36": "RES-HOLD-031",
    "D15-36": "RES-HOLD-057",
    "D17-36": "RES-HOLD-061",
    "D13-31": "RES-PG-0021",
    "D13-31A": "RES-PG-0021",
}

TASK_DEPENDENCIES: dict[str, str] = {
    "D5-DS01": "Issue #16 authoritative packages; D3 SourceRevision lifecycle",
    "D3-34": "D3-01..33 complete",
    "D7-PIC-01": "D7-01..36 baseline; see D07-PRODUCTION-IDENTITY-CLOSURE",
    "D12-CORE-01": "D3 SourceRevision; issue #35",
    "D12-CORE-02": "D12-CORE-01",
    "D12-CORE-03": "D6 validation evidence; D9 where available",
    "D12-CORE-04": "D12-CORE-03",
    "D12-CORE-05": "D12-CORE-04",
    "D12-CORE-06": "D12-CORE-01..05 adversarial tests",
    "D15-R3-01": "D15-10 mastery/history ORM boundary; RES-HOLD-057",
    "D17-F07": "D17-36; held PR61 CI255/257",
}

PRESERVED_SCOPE_TECH = frozenset({"SOURCE_PENDING", "BLOCKED", "NOT_STARTED", "DEFERRED"})


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
        "D12-CORE-01": "C07",
        "D12-CORE-02": "C07",
        "D12-CORE-03": "C07",
        "D12-CORE-04": "C07",
        "D12-CORE-05": "C07",
        "D12-CORE-06": "C07",
        "D12-ISSUE-44": "C07",
        "D12-ISSUE-45": "C07",
    }
    if task_id.startswith("D12-CORE-"):
        return "C07"
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


def path_exists_at_baseline(rel: str) -> bool:
    clean = rel.strip("`").split("`")[0].split(" ")[0]
    if not clean or clean.startswith("scope_map"):
        return False
    if "git show" in clean or "HELD" in clean:
        return False
    if not (clean.startswith("backend/") or clean.startswith("tests/") or clean.startswith("frontend/")):
        return False
    try:
        subprocess.check_output(
            ["git", "cat-file", "-e", f"{FROZEN_BASELINE}:{clean}"],
            cwd=REPO,
            stderr=subprocess.DEVNULL,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def enrich_scope(row: TaskRow, ev: dict[str, str], scope_authority: str, held: bool = False) -> None:
    hs = ev.get("historical_scope_state") or ""
    row.current_baseline_evidence = (
        f"scope_map@{scope_authority}; historical_state={hs or 'NOT_RECORDED'}"
    )
    row.historical_scope_state = hs
    ref = (ev.get("impl_ref") or "").strip("`")
    if held:
        row.baseline_code_path = f"HELD_EVIDENCE_ONLY@{scope_authority}; impl_ref={ref[:120]}"
    elif path_exists_at_baseline(ref):
        row.baseline_code_path = ref.split("`")[0][:200]
    elif ref and ref not in row.original_requirement:
        row.baseline_code_path = "NOT_VERIFIED: scope-map ref not present at frozen baseline"
    test = ev.get("test_ref") or ""
    if test:
        t = test.strip("`")
        row.test_path = t if path_exists_at_baseline(t) else f"NOT_VERIFIED: {t[:120]}"


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
    hs_raw = (row.historical_scope_state or "").strip()
    hs = hs_raw.upper()
    if row.task_id.startswith("D11-") and hs == "PASS":
        row.engineering_acceptance_state = "HISTORICAL_ACCEPTED"
        row.technical_acceptance_state = "NOT_VERIFIED"
    elif hs in PRESERVED_SCOPE_TECH or hs_raw in PRESERVED_SCOPE_TECH:
        row.engineering_acceptance_state = f"HISTORICAL_SCOPE_{hs or hs_raw.upper()}"
        row.technical_acceptance_state = hs if hs else hs_raw.upper()
    elif hs == "PASS":
        row.engineering_acceptance_state = "HISTORICAL_ACCEPTED"
        row.technical_acceptance_state = "NOT_VERIFIED"
    elif hs:
        row.engineering_acceptance_state = f"HISTORICAL_SCOPE_{hs}"
        row.technical_acceptance_state = tech_default
    else:
        row.technical_acceptance_state = tech_default
    row.current_test_execution_state = "NOT_RUN"
    row.current_static_inspection_state = "NOT_RUN"
    if row.day in {"Day11", "Day15", "Day17"}:
        row.external_evidence = "HELD_UNMERGED: code not on develop@8b71aa03"
    elif row.day in {"Day12", "Day13", "Day14", "Day16", "Day18"}:
        row.external_evidence = "FOUNDER_MILESTONE_ONLY: merged with deferred acceptance"


def load_github_snapshot() -> dict[int, dict]:
    path = EXEC / "C00-GITHUB-AUTHORITY-SNAPSHOT.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {int(i["issue"]): i for i in payload.get("issues", []) if "issue" in i}


def issue_authority_locator(issue: int, snap: dict[int, dict]) -> str:
    meta = snap.get(issue, {})
    if meta.get("body_sha256") in {"", "UNAVAILABLE"}:
        return f"MISSING_SPEC: GitHub issue #{issue} body unavailable to Cursor audit"
    sha = meta["body_sha256"]
    when = meta.get("retrieved_at_utc", "unknown")
    return f"GitHub issue #{issue} body_sha256={sha} retrieved_at={when}"


def finalize_row(row: TaskRow) -> None:
    row.closure_workstream = closure_workstream(row.task_id)
    apply_day_history(row)
    if row.task_id == "D5-DS01":
        row.engineering_acceptance_state = "DEFERRED"
        row.technical_acceptance_state = "SOURCE_PENDING"
        row.external_evidence = "Issue #16; Founder deferred authoritative Telangana packages"
        row.residual_finding_ids = "RES-SRC-016"
    dep = TASK_DEPENDENCIES.get(row.task_id)
    if dep:
        row.dependencies = dep
    elif row.dependencies == "NOT_VERIFIED":
        day_dep = {
            "Day1": f"develop@{FROZEN_BASELINE[:12]} foundation",
            "Day4": "Issue #12 official source deferral; D3 SourceRevision",
            "Day5": "D3-D4 baseline; D5-DS01/issue #16 deferred",
            "Day11": "Held PR #31; RES-HOLD-031",
            "Day12": "Merged milestone PR #34; issues #35/#44/#45 separate streams",
            "Day15": "Held PR #57; trusted runtime boundary",
            "Day17": "Held PR #61; auth/jobs boundary",
        }.get(row.day)
        row.dependencies = day_dep or (
            f"Prior day scope per execution-state; cross-workstream map in C00-RESIDUALS "
            f"(independent per-task graph NOT_VERIFIED)"
        )
    res = RESIDUAL_BY_TASK.get(row.task_id, "")
    if not row.residual_finding_ids and res:
        row.residual_finding_ids = res
    if row.task_id.startswith("D12-CORE-"):
        row.residual_finding_ids = row.residual_finding_ids or "RES-D12-CORE"
    if "MISSING_SPEC" not in row.original_authority and row.acceptance_criterion.startswith("NOT_VERIFIED"):
        row.acceptance_proof = f"Pending: reconcile acceptance_criterion against {row.original_authority}"
    elif not row.acceptance_criterion.startswith("NOT_VERIFIED"):
        row.acceptance_proof = (
            f"Stated acceptance (authority excerpt): {row.acceptance_criterion[:240]}"
            + ("…" if len(row.acceptance_criterion) > 240 else "")
        )
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

    d6auth = "docs/execution/D06-EDUCATION-INTELLIGENCE-VALIDATORS.md"
    d6text = read_text(EXEC / "D06-EDUCATION-INTELLIGENCE-VALIDATORS.md")
    for t in parse_two_column_summary_table(d6text, "D6-", d6auth, "Day6"):
        put(t)
    for t in parse_d6_amendments(read_text(EXEC / "D06-DELIVERY-EVIDENCE.md"), "docs/execution/D06-DELIVERY-EVIDENCE.md"):
        put(t, parent="D6-36")

    d10auth = "docs/execution/D10-PREREQUISITES-ROOT-CAUSE-DIAGNOSTICS.md"
    d10text = read_text(EXEC / "D10-PREREQUISITES-ROOT-CAUSE-DIAGNOSTICS.md")
    for t in parse_three_column_task_table(d10text, "D10-", d10auth, "Day10"):
        put(t)

    day_heading_specs = {
        7: "D07-KNOWLEDGE-INTELLIGENCE-ANYTHINGLLM.md",
        8: "D08-LANGGRAPH-ORCHESTRATION.md",
        9: "D09-DIAGNOSTIC-DISTRACTOR-INTELLIGENCE.md",
    }
    for num, fname in day_heading_specs.items():
        prefix = f"D{num}"
        pat = re.compile(rf"{prefix}-\d{{2}}")
        spec_path = EXEC / fname
        auth = str(spec_path.relative_to(REPO))
        for t in parse_heading_tasks(read_text(spec_path), pat, auth, f"Day{num}"):
            put(t)

    gh_snap = load_github_snapshot()
    for issue_no, (prefix, day) in GITHUB_ISSUE_MAP.items():
        meta = gh_snap.get(issue_no, {})
        body = meta.get("body") or ""
        auth = issue_authority_locator(issue_no, gh_snap)
        if not body:
            continue
        for t in parse_github_authority_tables(body, f"{prefix}-", auth, day):
            put(t)

    iss35 = gh_snap.get(35, {})
    if iss35.get("body"):
        auth35 = issue_authority_locator(35, gh_snap)
        for t in parse_d12_core_workstream(iss35["body"], auth35):
            put(t, parent="D12-36")

    for t in parse_d7_pic(read_text(EXEC / "D07-PRODUCTION-IDENTITY-CLOSURE.md"), "docs/execution/D07-PRODUCTION-IDENTITY-CLOSURE.md"):
        put(t, parent="D7-36")

    d11_spec = git_show(HELD_D11, "docs/execution/D11-JEE-MAIN-EXAM-INTELLIGENCE.md") or ""
    d11auth = f"git show {HELD_D11}:docs/execution/D11-JEE-MAIN-EXAM-INTELLIGENCE.md; GitHub issue #30"
    for t in parse_pipe_authoritative_table(d11_spec, "D11", d11auth, "Day11"):
        put(t)

    for issue_no, tid, parent, req in [
        (44, "D12-ISSUE-44", "D12-36", "Day12 one-shot comprehensive closure #44"),
        (45, "D12-ISSUE-45", "D12-36", "Day12 consolidated acceptance fix #45"),
    ]:
        auth = issue_authority_locator(issue_no, gh_snap)
        rows[tid] = TaskRow(
            tid,
            "Day12",
            auth,
            req,
            f"{auth} — Founder-authorized separate closure obligation",
            parent_task_id=parent,
            approved_amendments=tid,
            residual_finding_ids=f"RES-D12-ISSUE-{issue_no}",
        )

    amendments = [
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
        (
            "D15-R3-01",
            "D15-30",
            "Day15",
            "PR #57 review comment 7133926987 (MS01 callable ORM boundary)",
            "All callable ORM attribute loads blocked; implicit refresh on expired instances violates seal",
            "MS01: attempt_meta/mastery/diagnostics/history paths may lazy-load expired ORM",
        ),
        (
            "D15-R3-02",
            "D15-15",
            "Day15",
            "PR #57 review comment 7133926987 (MS02)",
            "history/memory None without ORM reads; ELIGIBLE enum not authority",
            "MS02: runtime eligibility BLOCKED_UNVERIFIED; structural catalog ELIGIBLE retained",
        ),
        (
            "D15-R3-03",
            "D15-36",
            "Day15",
            "PR #57 review comment 7133926987 (MS03)",
            "Test scope insufficient for complete callable-boundary seal",
            "MS03: no execute/begin_nested spies; fixture refresh masks expiry",
        ),
        (
            "D15-R3-04",
            "D15-30",
            "Day15",
            "PR #57 review comment 7133926987 (MS04)",
            "Ledger stale scope descriptions; verifier gates partial only",
            "MS04: 0 PASS / 35 PARTIAL / 1 NOT_STARTED retained but misleading text",
        ),
        (
            "D15-R3-05",
            "D15-36",
            "Day15",
            "PR #57 review comment 7133926987",
            "Complete containment rejected despite targeted CI green",
            "No merge/Day16 unlock per STOP_AND_ESCALATE",
        ),
        (
            "D15-R3-06",
            "D15-36",
            "Day15",
            "PR #57 review comment 7133926987",
            "D15-36 Founder signoff still pending",
            "Final authorized seal consumed on held head",
        ),
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
        held_scope = loc.startswith("git show")
        for tid, ev in evmap.items():
            if tid not in rows:
                rows[tid] = TaskRow(
                    tid,
                    day,
                    f"MISSING_SPEC: {tid} not in authoritative spec extracted this candidate",
                    ev.get("scope_summary", "UNKNOWN"),
                    "NOT_VERIFIED: no authoritative requirement located",
                )
            enrich_scope(rows[tid], ev, loc, held=held_scope)

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