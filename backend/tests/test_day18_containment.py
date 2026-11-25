from app.frontend_product.containment import (
    allowed_endpoints_file_integrity,
    catalogue_json_integrity,
    resolve_frontend_root,
    student_fixture_file_integrity,
    summarize_required_frontend_paths,
)


def test_student_fixture_excludes_answer_keys() -> None:
    root = resolve_frontend_root()
    ok, issues = student_fixture_file_integrity(root)
    assert ok, issues


def test_allowed_endpoints_whitelist_merged_only() -> None:
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