from app.frontend_product.containment import (
    allowed_endpoints_file_integrity,
    built_bundle_integrity,
    catalogue_json_integrity,
    resolve_frontend_root,
    student_fixture_file_integrity,
    summarize_required_frontend_paths,
    teacher_fixture_file_integrity,
)


def test_student_fixture_excludes_answer_keys() -> None:
    root = resolve_frontend_root()
    ok, issues = student_fixture_file_integrity(root)
    assert ok, issues


def test_teacher_fixture_omits_answer_payload_keys() -> None:
    root = resolve_frontend_root()
    ok, issues = teacher_fixture_file_integrity(root)
    assert ok, issues


def test_allowed_endpoints_exact_whitelist() -> None:
    root = resolve_frontend_root()
    ok, issues = allowed_endpoints_file_integrity(root)
    assert ok, issues


def test_catalogue_declares_non_authoritative() -> None:
    root = resolve_frontend_root()
    ok, issues = catalogue_json_integrity(root)
    assert ok, issues


def test_required_frontend_paths_present() -> None:
    root = resolve_frontend_root()
    paths = summarize_required_frontend_paths(root)
    assert all(paths.values()), paths


def test_built_bundle_has_no_answer_key_strings_when_present() -> None:
    root = resolve_frontend_root()
    ok, issues, status = built_bundle_integrity(root)
    assert status in {"SCANNED", "NOT_BUILT_SKIP"}
    if status == "SCANNED":
        assert ok, issues