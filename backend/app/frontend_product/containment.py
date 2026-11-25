"""Static containment checks for Day 18 frontend boundaries."""

from __future__ import annotations

from pathlib import Path

ALLOWED_MERGED_PATHS = frozenset({"/health", "/ready", "/api/v1/system/info"})

STUDENT_FORBIDDEN_KEYS = frozenset(
    {"correctAnswer", "answerKey", "explanation", "isCorrect"},
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
        if f"{key}:" in text.replace(" ", ""):
            issues.append(f"STUDENT_FIXTURE_CONTAINS_{key}")
    return (len(issues) == 0, tuple(issues))


def allowed_endpoints_file_integrity(frontend_root: Path) -> tuple[bool, tuple[str, ...]]:
    path = frontend_root / "src" / "contracts" / "allowed-endpoints.ts"
    if not path.is_file():
        return False, ("MISSING_ALLOWED_ENDPOINTS_FILE",)
    text = path.read_text(encoding="utf-8")
    issues: list[str] = []
    for required in ALLOWED_MERGED_PATHS:
        if required not in text:
            issues.append(f"MISSING_ALLOWED_PATH:{required}")
    return (len(issues) == 0, tuple(issues))


def catalogue_json_integrity(frontend_root: Path) -> tuple[bool, tuple[str, ...]]:
    path = frontend_root / "src" / "fixtures" / "catalogue.ts"
    if not path.is_file():
        return False, ("MISSING_CATALOGUE_FILE",)
    text = path.read_text(encoding="utf-8")
    issues: list[str] = []
    if "answerKeysInStudentBundle: false" not in text:
        issues.append("CATALOGUE_ANSWER_KEY_FLAG_FALSE_REQUIRED")
    if "authoritative: false" not in text:
        issues.append("CATALOGUE_NOT_AUTHORITATIVE")
    return (len(issues) == 0, tuple(issues))


def summarize_required_frontend_paths(frontend_root: Path) -> dict[str, bool]:
    required = [
        "src/app/App.tsx",
        "src/app/ProductShell.tsx",
        "src/capability/readiness.ts",
        "src/features/studio/QuestionStudioPage.tsx",
        "src/features/student/StudentRunnerPage.tsx",
        "e2e/day18.spec.ts",
    ]
    return {rel: (frontend_root / rel).is_file() for rel in required}