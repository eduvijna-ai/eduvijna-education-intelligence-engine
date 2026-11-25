from pathlib import Path

from app.frontend_product.scope_ledger import (
    load_repo_scope_counts,
    resolve_scope_map_path,
    validate_scope_map_integrity,
)


def test_day18_scope_map_has_36_unique_rows() -> None:
    path = resolve_scope_map_path()
    assert path.is_file(), path
    md = path.read_text(encoding="utf-8")
    ok, issues = validate_scope_map_integrity(md)
    assert ok, issues
    counts = load_repo_scope_counts(Path(__file__).resolve().parents[2])
    assert counts["TOTAL"] == 36
    assert counts["NOT_STARTED"] == 1
    assert counts["PARTIAL"] == 35