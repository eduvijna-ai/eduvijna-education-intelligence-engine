from pathlib import Path

from app.learner_intelligence.enums import MasteryLevel
from app.learner_intelligence.mastery import compute_mastery_from_events
from app.learner_intelligence.scope_ledger import load_repo_scope_counts


def test_scope_ledger_unique_36_rows() -> None:
    counts = load_repo_scope_counts()
    assert counts["TOTAL"] == 36
    assert counts["NOT_STARTED"] >= 1


def test_mastery_cold_start_unknown() -> None:
    snap = compute_mastery_from_events(
        [],
        concept_code="arithmetic.addition",
        organization_id="o",
        learner_id="l",
    )
    assert snap.level == MasteryLevel.UNKNOWN


def test_mastery_blank_excluded_from_support() -> None:
    from app.learner_intelligence.enums import ScoringVerdict
    from app.models.learner_intelligence import ScoreEvidenceEvent as Event

    events = [
        Event(
            organization_id="o",
            learner_id="l",
            attempt_id="a",
            item_sequence=1,
            verdict=ScoringVerdict.BLANK.value,
            marks_awarded=0,
            max_marks=4,
            snapshot_fingerprint="x",
            concept_codes_json=["arithmetic.addition"],
        )
    ]
    snap = compute_mastery_from_events(
        events,
        concept_code="arithmetic.addition",
        organization_id="o",
        learner_id="l",
    )
    assert snap.level == MasteryLevel.UNKNOWN


def test_alembic_upgrade_head_sqlite(tmp_path: Path) -> None:
    from alembic import command
    from alembic.config import Config

    backend_root = Path(__file__).resolve().parents[1]
    db = tmp_path / "alembic.db"
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    cfg.set_main_option("script_location", str(backend_root / "migrations"))
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "20261124_0021")
    command.upgrade(cfg, "20261124_0022")
