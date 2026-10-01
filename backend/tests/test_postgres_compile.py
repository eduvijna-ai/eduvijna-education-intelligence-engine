from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

import app.models  # noqa: F401
from app.db.base import Base


def test_all_canonical_tables_compile_for_postgresql() -> None:
    dialect = postgresql.dialect()
    compiled = [
        str(CreateTable(table).compile(dialect=dialect))
        for table in Base.metadata.sorted_tables
    ]
    assert compiled
    assert any("curriculum_versions" in statement for statement in compiled)
    assert any("exam_blueprint_rules" in statement for statement in compiled)
    assert any("questions" in statement for statement in compiled)
