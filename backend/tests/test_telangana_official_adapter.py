"""Synthetic adapter checks; these never constitute official evidence."""

from types import SimpleNamespace
from typing import Any

import pytest

from app.curriculum_intelligence.telangana_official import (
    _chapter_by_title,
    _materialize_chapter_path,
    official_telangana_demonstration,
)
from app.curriculum_intelligence.telangana_syllabus import (
    ParsedChapter,
    TelanganaSyllabusParseError,
)

DIMENSIONS = {
    "course_family": "General",
    "course_group": "Group A",
    "subject_language": "not_applicable",
    "language_role": "not_applicable",
    "book_part": "Part 1",
    "bilingual": "no",
}
SCOPE_DIMENSIONS = {
    "course_families": ["General"],
    "course_groups": ["Group A", "Group B"],
    "subject_languages": ["not_applicable"],
    "language_roles": ["not_applicable"],
    "book_parts": ["Part 1"],
    "bilingual_states": ["no"],
}


def test_exact_chapter_selection_no_prefix_guess() -> None:
    chapter = ParsedChapter("1", "Force and pressure", "page 1", ())
    with pytest.raises(TelanganaSyllabusParseError):
        _chapter_by_title((chapter,), "Force")


def test_subject_codes_disjoint_and_derived_labels_explicit() -> None:
    specs: list[Any] = []

    class Service:
        def upsert_nodes(self, **kwargs: Any) -> dict[str, Any]:
            specs.extend(kwargs["specs"])
            return {spec.code: SimpleNamespace(id=spec.code) for spec in kwargs["specs"]}

        def curriculum_path(self, node_id: str) -> Any:
            return SimpleNamespace(model_dump=lambda **kwargs: {"id": node_id})

    chapter = ParsedChapter("1", "Force", "page 1, section 1", ("Types",), ("page 1, section 1.1",))
    for subject in ["Physical Science", "Biological Science"]:
        _materialize_chapter_path(
            Service(),
            version=None,
            revision=None,
            grade="VIII",
            medium="English",
            subject=subject,
            chapter=chapter,
            applicability=DIMENSIONS,
        )  # type: ignore[arg-type]
    left, right = specs[:7], specs[7:]
    assert {s.code for s in left[2:]}.isdisjoint(s.code for s in right[2:])
    assert left[0].metadata_json["identity"] == {"grade": "VIII", **DIMENSIONS}
    for spec in left:
        if spec.node_type in {"unit", "concept", "grade_year", "medium", "subject"}:
            assert spec.official_text is None
            assert spec.metadata_json["label_status"] == "derived"
    assert left[-2].source_locator == "page 1, section 1.1"


def test_annual_plan_bytes_never_establish_pack(tmp_path: Any) -> None:
    (tmp_path / "day5-verification-slice.json").write_text('{"slices": {}}')

    class Service:
        def has_source_content(self, revision: Any) -> bool:
            return True

        def is_registry_only(self, revision: Any) -> bool:
            return False

        def ensure_pack(self, **kwargs: Any) -> None:
            pytest.fail("Annual plan cannot establish a curriculum pack")

    report = official_telangana_demonstration(
        Service(),
        {  # type: ignore[arg-type]
            "tgbie-maths-ia-annual-plan-2025-26": SimpleNamespace(),
        },
        content_root=tmp_path,
    )
    assert report["materialized_slices"] == []
    assert any(
        "governing_syllabus_required" in reason for reason in report["unresolved_materialization"]
    )


def test_reviewed_preflight_accepts_exact_frozen_source_and_rejects_changes(
    monkeypatch: Any,
) -> None:
    """Synthetic boundary doubles exercise every frozen dimension, not the official gate."""
    from copy import deepcopy

    import app.curriculum_intelligence.telangana_official as adapter
    from app.curriculum_intelligence.telangana_syllabus import ParsedSyllabus

    chapter = ParsedChapter(
        "1",
        "Force",
        "page 1, line 3, section 1. Force",
        ("Types",),
        ("page 1, line 4, section 1.1",),
    )
    metadata = {
        "synthetic": False,
        "document_type": "syllabus",
        "verified_locators": [
            "page 1 applicability",
            chapter.locator,
            chapter.topic_locators[0],
        ],
    }
    revision = SimpleNamespace(
        id="revision",
        checksum="a" * 64,
        storage_path="private.pdf",
        source_snapshot_checksum="b" * 64,
        extracted_text="Force Types",
        metadata_json={
            "source_snapshot": {"url": "https://official.invalid/pdf", "metadata_json": metadata}
        },
    )
    scope = SimpleNamespace(
        **SCOPE_DIMENSIONS,
        pack_code="ts-scert",
        version_codes=("reviewed-2025",),
        grades=("VIII",),
        media=("English",),
        subjects=("Physical Science",),
        publication_status="final",
        applicability_status="verified",
        applicability_locator="page 1 applicability",
    )
    service = SimpleNamespace(
        _source_metadata=lambda _: metadata,
        source_service=SimpleNamespace(storage=SimpleNamespace(read=lambda _: b"pdf")),
    )
    frozen = {
        **DIMENSIONS,
        "key": "synthetic-check",
        "chapter": "1. Force",
        "academic_version": "reviewed-2025",
        "pack_code": "ts-scert",
        "grade": "VIII",
        "medium": "English",
        "subject": "Physical Science",
        "source_checksum": revision.checksum,
        "source_revision": revision.id,
        "source_locator": chapter.locator,
        "topic_locator": chapter.topic_locators[0],
    }
    monkeypatch.setattr(adapter, "exact_scope", lambda *_: scope)
    monkeypatch.setattr(
        adapter,
        "parse_scert_syllabus_pdf",
        lambda *args, **kwargs: ParsedSyllabus(
            "unknown-year", "Physical Science", (chapter,), "VIII"
        ),
    )
    assert adapter._reviewed_chapter(service, revision, frozen) == chapter
    portable = deepcopy(frozen)
    portable.pop("source_revision")
    portable.update(source_url="https://official.invalid/pdf", source_snapshot_checksum="b" * 64)
    assert adapter._reviewed_chapter(service, revision, portable) == chapter
    for field, wrong in [
        ("medium", "Telugu"),
        ("grade", "IX"),
        ("subject", "Biological Science"),
        ("academic_version", "2026"),
        ("source_revision", "wrong"),
        ("source_checksum", "0" * 64),
        ("source_locator", "wrong"),
        ("topic_locator", "wrong"),
        ("chapter", "1. Friction"),
    ]:
        changed = {**frozen, field: wrong}
        with pytest.raises(TelanganaSyllabusParseError):
            adapter._reviewed_chapter(service, revision, changed)
    for field in DIMENSIONS:
        missing = {key: value for key, value in frozen.items() if key != field}
        with pytest.raises(TelanganaSyllabusParseError, match="Incomplete frozen"):
            adapter._reviewed_chapter(service, revision, missing)
        for invalid in ("unknown", "not_sourced", "not_applicable"):
            if invalid == DIMENSIONS[field]:
                continue
            with pytest.raises(TelanganaSyllabusParseError, match="outside reviewed"):
                adapter._reviewed_chapter(service, revision, {**frozen, field: invalid})
    metadata["document_type"] = "annual_plan"
    with pytest.raises(TelanganaSyllabusParseError, match="Governing syllabus"):
        adapter._reviewed_chapter(service, revision, frozen)


def test_fresh_database_reviewed_contract_materializes_and_failed_slice_rolls_back(
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    """Isolated fake official-source lifecycle; never used by live acceptance."""
    import json
    from io import BytesIO

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    import app.models  # noqa: F401
    from app.curriculum_intelligence.service import CurriculumIntelligenceService
    from app.curriculum_intelligence.telangana_syllabus import parse_scert_syllabus_pdf
    from app.db.base import Base
    from app.db.session import create_database_engine
    from app.models.curriculum import CurriculumNode, CurriculumPack, CurriculumVersion
    from app.models.enums import SourceIngestionMethod, SourceTrustTier, SourceType
    from app.schemas.source_intelligence import SourceRegistrationInput
    from app.source_intelligence.service import SourceIntelligenceService
    from app.source_intelligence.storage import LocalSourceStorage

    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    lines = [
        "PHYSICAL SCIENCE",
        "VIII CLASS",
        "1. Force",
        "1.1 Types of forces",
        "SYNTHETIC TEST DOCUMENT ONLY. Academic applicability review fixture.",
    ]
    stream.set_data(
        (
            "BT /F1 12 Tf 50 750 Td 20 TL " + " ".join(f"({line}) Tj T*" for line in lines) + " ET"
        ).encode()
    )
    page[NameObject("/Contents")] = stream
    buffer = BytesIO()
    writer.write(buffer)
    content = buffer.getvalue()
    chapter = parse_scert_syllabus_pdf(content).chapters[0]
    engine = create_database_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        sources = SourceIntelligenceService(
            session, storage=LocalSourceStorage(tmp_path / "sources")
        )
        service = CurriculumIntelligenceService(session, source_service=sources)
        source = sources.register_source(
            SourceRegistrationInput(
                source_type=SourceType.OFFICIAL_SYLLABUS,
                title="SYNTHETIC official-adapter test",
                url="https://synthetic.example.invalid/governing.pdf",
                authority="Synthetic test authority",
                country="India",
                board_or_exam="ts-scert",
                academic_year="2025-26",
                copyright_classification="synthetic_fixture",
                trust_tier=SourceTrustTier.OFFICIAL_PRIMARY,
                metadata_json={
                    "synthetic": False,
                    "document_type": "syllabus",
                    "verified_locators": [
                        chapter.locator,
                        chapter.topic_locators[0],
                        "review section",
                    ],
                    "curriculum_scope": {
                        **SCOPE_DIMENSIONS,
                        "pack_code": "ts-scert",
                        "version_codes": ["reviewed-test"],
                        "grades": ["VIII"],
                        "media": ["English"],
                        "subjects": ["Physical Science"],
                        "publication_status": "final",
                        "applicability_status": "verified",
                        "applicability_locator": "review section",
                    },
                },
            ),
            actor_id="synthetic-test",
        )
        revision = sources.ingest_upload(
            source.id,
            method=SourceIngestionMethod.PDF,
            filename="synthetic.pdf",
            content=content,
            actor_id="synthetic-test",
        )
        sources.extract_revision(revision.id, actor_id="synthetic-test")
        sources.create_diff(revision.id, actor_id="synthetic-test")
        assert sources.validate_revision(revision.id, actor_id="synthetic-test").valid
        sources.approve_revision(revision.id, actor_id="synthetic-test")
        revision = sources.activate_revision(revision.id, actor_id="synthetic-test")
        frozen = {
            **DIMENSIONS,
            "source_manifest_key": "test-governing",
            "pack_name": "Synthetic SCERT adapter test",
            "pack_code": "ts-scert",
            "academic_version": "reviewed-test",
            "academic_year": "2025-26",
            "grade": "VIII",
            "medium": "English",
            "subject": "Physical Science",
            "chapter": "1. Force",
            "source_checksum": revision.checksum,
            "source_url": source.url,
            "source_snapshot_checksum": revision.source_snapshot_checksum,
            "source_locator": chapter.locator,
            "topic_locator": chapter.topic_locators[0],
        }
        contract = tmp_path / "day5-verification-slice.json"
        # No runtime UUID is required. Invalid academic identity rolls back a fresh attempt.
        contract.write_text(
            json.dumps({"slices": {"positive": {**frozen, "academic_year": "wrong"}}})
        )
        failed = official_telangana_demonstration(
            service, {"test-governing": revision}, content_root=tmp_path
        )
        assert not failed["materialized_slices"]
        assert session.scalar(select(func.count()).select_from(CurriculumPack)) == 0
        contract.write_text(json.dumps({"slices": {"positive": frozen}}))
        with monkeypatch.context() as patch:

            def reject_nodes(**kwargs: Any) -> None:
                raise ValueError("synthetic node-write failure after pack creation")

            patch.setattr(service, "upsert_nodes", reject_nodes)
            failed_write = official_telangana_demonstration(
                service,
                {"test-governing": revision},
                content_root=tmp_path,
            )
            assert not failed_write["materialized_slices"]
            assert session.scalar(select(func.count()).select_from(CurriculumPack)) == 0
            assert session.scalar(select(func.count()).select_from(CurriculumVersion)) == 0
        report = official_telangana_demonstration(
            service, {"test-governing": revision}, content_root=tmp_path
        )
        assert len(report["materialized_slices"]) == 1, report["unresolved_materialization"]
        assert session.scalar(select(func.count()).select_from(CurriculumNode)) == 7
        assert session.scalar(select(func.count()).select_from(CurriculumVersion)) == 1
        assert session.scalar(select(CurriculumPack)).framework_id is None
        repeated = official_telangana_demonstration(
            service, {"test-governing": revision}, content_root=tmp_path
        )
        assert repeated["materialized_slices"] == report["materialized_slices"]
        assert session.scalar(select(func.count()).select_from(CurriculumNode)) == 7
        # A second explicitly sourced group receives disjoint nodes, not a rebind.
        contract.write_text(
            json.dumps(
                {
                    "slices": {
                        "group-b": {**frozen, "course_group": "Group B"},
                    }
                }
            )
        )
        second_group = official_telangana_demonstration(
            service,
            {"test-governing": revision},
            content_root=tmp_path,
        )
        assert len(second_group["materialized_slices"]) == 1
        assert session.scalar(select(func.count()).select_from(CurriculumNode)) == 14
        session.commit()
        session.expunge_all()
        from app.curriculum_intelligence.scoped_curriculum import query_scoped_paths

        base = {
            "pack_code": "ts-scert",
            "version_code": "reviewed-test",
            "grade": "VIII",
            "medium": "English",
            "subject": "Physical Science",
        }
        matched = query_scoped_paths(service, **base, **DIMENSIONS)
        assert matched["status"] == "matched"
        assert len(matched["paths"]) == 1
        missing = query_scoped_paths(service, **base)
        assert missing["status"] == "ambiguous"
        assert not missing["paths"]
        assert "course_group" in missing["unresolved_dimensions"]
        wrong = query_scoped_paths(service, **base, **{**DIMENSIONS, "course_group": "Group Z"})
        assert wrong["status"] == "no_match"
        leaf = session.get(CurriculumNode, matched["paths"][0]["node_ids"][-1])
        assert leaf is not None
        for dimension, value in DIMENSIONS.items():
            assert leaf.metadata_json["identity"][dimension] == value
            assert all(
                node.metadata_json["identity"][dimension] == value
                for node in service.hierarchy_path(leaf.id)
            )
    engine.dispose()
