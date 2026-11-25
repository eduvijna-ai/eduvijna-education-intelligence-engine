"""Static containment checks for Day 18 frontend boundaries."""

from __future__ import annotations

import re
from pathlib import Path

ALLOWED_MERGED_ENDPOINTS = (
    ("GET", "/health"),
    ("GET", "/ready"),
    ("GET", "/api/v1/system/info"),
)
ALLOWED_MERGED_PATHS = frozenset(p for _, p in ALLOWED_MERGED_ENDPOINTS)

STUDENT_ALLOWED_KEYS = frozenset(
    {"id", "stem", "type", "options", "maxMarks"},
)
STUDENT_FORBIDDEN_KEYS = frozenset(
    {"correctAnswer", "answerKey", "explanation", "isCorrect"},
)

TEACHER_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {"correctAnswer", "answerKey", "isCorrect"},
)

TEACHER_ANSWER_REVEALING_PHRASES = (
    "matching total displacement over total time",
    "ds/dt",
)

FORBIDDEN_BUNDLE_SUBSTRINGS = (
    "correctAnswer",
    "answerKey",
    "isCorrect",
)


def resolve_frontend_root() -> Path:
    here = Path(__file__).resolve()
    candidates = (
        here.parents[3] / "frontend",
        here.parents[2] / "frontend",
        Path("/app/frontend"),
    )
    for path in candidates:
        if path.is_dir():
            return path
    return candidates[0]


def frontend_available(frontend_root: Path) -> bool:
    return (frontend_root / "package.json").is_file()


def student_fixture_file_integrity(frontend_root: Path) -> tuple[bool, tuple[str, ...]]:
    path = frontend_root / "src" / "fixtures" / "questions-student.ts"
    if not path.is_file():
        return False, ("MISSING_STUDENT_FIXTURE_FILE",)
    text = path.read_text(encoding="utf-8")
    issues: list[str] = []
    for key in STUDENT_FORBIDDEN_KEYS:
        if re.search(rf"\b{re.escape(key)}\s*:", text):
            issues.append(f"STUDENT_FIXTURE_CONTAINS_{key}")
    if "STUDENT_RUNNER_FIXTURES" not in text:
        issues.append("STUDENT_FIXTURES_MISSING")
    for key in sorted(STUDENT_ALLOWED_KEYS):
        if key not in text:
            issues.append(f"STUDENT_FIXTURE_TYPE_MISSING_{key}")
    return (len(issues) == 0, tuple(issues))


def teacher_fixture_file_integrity(frontend_root: Path) -> tuple[bool, tuple[str, ...]]:
    path = frontend_root / "src" / "fixtures" / "questions-teacher.ts"
    if not path.is_file():
        return False, ("MISSING_TEACHER_FIXTURE_FILE",)
    text = path.read_text(encoding="utf-8")
    issues: list[str] = []
    for key in TEACHER_FORBIDDEN_PAYLOAD_KEYS:
        if re.search(rf"\b{re.escape(key)}\s*:", text):
            issues.append(f"TEACHER_FIXTURE_CONTAINS_{key}")
    if "answerMetadataStatus" not in text:
        issues.append("TEACHER_ANSWER_METADATA_STATUS_MISSING")
    lowered = text.lower()
    for phrase in TEACHER_ANSWER_REVEALING_PHRASES:
        if phrase.lower() in lowered:
            issues.append(f"TEACHER_ANSWER_REVEALING_PHRASE:{phrase}")
    return (len(issues) == 0, tuple(issues))


def allowed_endpoints_file_integrity(frontend_root: Path) -> tuple[bool, tuple[str, ...]]:
    path = frontend_root / "src" / "contracts" / "allowed-endpoints.ts"
    if not path.is_file():
        return False, ("MISSING_ALLOWED_ENDPOINTS_FILE",)
    text = path.read_text(encoding="utf-8")
    issues: list[str] = []
    pairs = re.findall(r"method:\s*'([^']+)',\s*path:\s*'([^']+)'", text)
    declared = {(m.upper(), p) for m, p in pairs}
    expected = set(ALLOWED_MERGED_ENDPOINTS)
    if declared != expected:
        issues.append("ALLOWED_ENDPOINT_PAIR_MISMATCH")
    if len(pairs) != len(set(pairs)):
        issues.append("ALLOWED_ENDPOINT_DUPLICATES")
    if "path.includes('?')" not in text and "includes('?')" not in text:
        issues.append("ALLOWED_PATH_QUERY_GUARD_MISSING")
    return (len(issues) == 0, tuple(issues))


def catalogue_json_integrity(frontend_root: Path) -> tuple[bool, tuple[str, ...]]:
    path = frontend_root / "src" / "fixtures" / "catalogue.ts"
    if not path.is_file():
        return False, ("MISSING_CATALOGUE_FILE",)
    text = path.read_text(encoding="utf-8")
    issues: list[str] = []
    if "answerKeysInClientBundle: false" not in text:
        issues.append("CATALOGUE_ANSWER_KEY_FLAG_FALSE_REQUIRED")
    if "authoritative: false" not in text:
        issues.append("CATALOGUE_NOT_AUTHORITATIVE")
    return (len(issues) == 0, tuple(issues))


def built_bundle_integrity(frontend_root: Path) -> tuple[bool, tuple[str, ...], str]:
    dist = frontend_root / "dist" / "assets"
    if not dist.is_dir():
        return False, ("DIST_NOT_BUILT",), "NOT_BUILT"
    assets = sorted(dist.glob("*.js"))
    if not assets:
        return False, ("DIST_ASSETS_EMPTY",), "EMPTY"
    issues: list[str] = []
    for asset in assets:
        text = asset.read_text(encoding="utf-8", errors="ignore")
        for needle in FORBIDDEN_BUNDLE_SUBSTRINGS:
            if needle in text:
                issues.append(f"BUNDLE_FORBIDDEN_SUBSTRING:{needle}:{asset.name}")
    return (len(issues) == 0, tuple(issues), "SCANNED")


def summarize_required_frontend_paths(frontend_root: Path) -> dict[str, bool]:
    required = [
        "src/app/App.tsx",
        "src/app/ProductShell.tsx",
        "src/capability/readiness.ts",
        "src/api/safeFetch.ts",
        "src/features/studio/QuestionStudioPage.tsx",
        "src/features/student/StudentRunnerPage.tsx",
        "e2e/day18.spec.ts",
    ]
    return {rel: (frontend_root / rel).is_file() for rel in required}


def _check_result(ok: bool, issues: tuple[str, ...], *, ran: bool) -> dict[str, object]:
    if not ran:
        return {"status": "SKIPPED", "ok": None, "issues": []}
    return {"status": "PASS" if ok else "FAIL", "ok": ok, "issues": list(issues)}


def run_frontend_containment_checks(
    frontend_root: Path,
    *,
    mode: str,
) -> dict[str, object]:
    if mode == "repo_backend_only":
        return {
            "mode": mode,
            "student_fixture": _check_result(False, (), ran=False),
            "teacher_fixture": _check_result(False, (), ran=False),
            "allowed_endpoints": _check_result(False, (), ran=False),
            "catalogue": _check_result(False, (), ran=False),
            "bundle": _check_result(False, (), ran=False),
            "paths": {"status": "SKIPPED", "ok": None, "issues": []},
            "all_ok": None,
        }

    s_ok, s_issues = student_fixture_file_integrity(frontend_root)
    t_ok, t_issues = teacher_fixture_file_integrity(frontend_root)
    a_ok, a_issues = allowed_endpoints_file_integrity(frontend_root)
    c_ok, c_issues = catalogue_json_integrity(frontend_root)
    b_ok, b_issues, b_status = built_bundle_integrity(frontend_root)
    paths = summarize_required_frontend_paths(frontend_root)
    paths_ok = all(paths.values())
    path_issues = () if paths_ok else tuple(sorted(k for k, v in paths.items() if not v))

    static_ok = s_ok and t_ok and a_ok and c_ok and paths_ok
    if b_status in {"NOT_BUILT", "EMPTY"}:
        bundle_payload: dict[str, object] = {
            "status": b_status,
            "ok": None,
            "issues": list(b_issues),
        }
        all_ok: bool | None = static_ok
    else:
        bundle_payload = {
            "status": "SCANNED" if b_ok else "FAIL",
            "ok": b_ok,
            "issues": list(b_issues),
        }
        all_ok = static_ok and b_ok

    return {
        "mode": mode,
        "student_fixture": _check_result(s_ok, s_issues, ran=True),
        "teacher_fixture": _check_result(t_ok, t_issues, ran=True),
        "allowed_endpoints": _check_result(a_ok, a_issues, ran=True),
        "catalogue": _check_result(c_ok, c_issues, ran=True),
        "bundle": bundle_payload,
        "paths": _check_result(paths_ok, path_issues, ran=True),
        "all_ok": all_ok,
    }