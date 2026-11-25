"""Static containment checks for Day 18 frontend boundaries."""

from __future__ import annotations

import re
from pathlib import Path

ALLOWED_MERGED_PATHS = frozenset({"/health", "/ready", "/api/v1/system/info"})

STUDENT_FORBIDDEN_KEYS = frozenset(
    {"correctAnswer", "answerKey", "explanation", "isCorrect"},
)

TEACHER_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {"correctAnswer", "answerKey", "isCorrect"},
)

FORBIDDEN_BUNDLE_SUBSTRINGS = (
    "correctAnswer",
    "answerKey",
    "isCorrect",
    '"explanation"',
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


def student_fixture_file_integrity(frontend_root: Path) -> tuple[bool, tuple[str, ...]]:
    path = frontend_root / "src" / "fixtures" / "questions-student.ts"
    if not path.is_file():
        return False, ("MISSING_STUDENT_FIXTURE_FILE",)
    text = path.read_text(encoding="utf-8")
    issues: list[str] = []
    for key in STUDENT_FORBIDDEN_KEYS:
        if re.search(rf"\b{re.escape(key)}\s*:", text):
            issues.append(f"STUDENT_FIXTURE_CONTAINS_{key}")
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
    return (len(issues) == 0, tuple(issues))


def allowed_endpoints_file_integrity(frontend_root: Path) -> tuple[bool, tuple[str, ...]]:
    path = frontend_root / "src" / "contracts" / "allowed-endpoints.ts"
    if not path.is_file():
        return False, ("MISSING_ALLOWED_ENDPOINTS_FILE",)
    text = path.read_text(encoding="utf-8")
    issues: list[str] = []
    declared = set(re.findall(r"path:\s*'([^']+)'", text))
    if declared != set(ALLOWED_MERGED_PATHS):
        extra = sorted(declared - ALLOWED_MERGED_PATHS)
        missing = sorted(ALLOWED_MERGED_PATHS - declared)
        if extra:
            issues.append(f"UNEXPECTED_ALLOWED_PATHS:{','.join(extra)}")
        if missing:
            issues.append(f"MISSING_ALLOWED_PATHS:{','.join(missing)}")
    if "GET" not in text:
        issues.append("ALLOWED_METHODS_NOT_GET_ONLY")
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
        return True, (), "NOT_BUILT_SKIP"
    issues: list[str] = []
    for asset in dist.glob("*.js"):
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


def frontend_available(frontend_root: Path) -> bool:
    return (frontend_root / "package.json").is_file()