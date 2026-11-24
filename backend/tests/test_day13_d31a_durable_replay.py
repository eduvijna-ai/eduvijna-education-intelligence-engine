from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import os
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.cuet_clat.constants import CLAT_PACK_CODE, CUET_PACK_CODE
from app.cuet_clat.durable_replay_envelope import (
    BLUEPRINT_PREFIX,
    D13ReplayIssueCode,
    D13ReplayScope,
    D13ReservationState,
    abort_reservation,
    build_request_fingerprint,
    confirmed_read_after_commit,
    derive_request_fingerprint,
    hash_idempotency_key,
    payload_checksum,
    publish_replay_result,
    read_replay_result,
    reserve_replay_slot,
    transition_to_in_progress,
)
from app.cuet_clat.exam_profile import ensure_synthetic_demo_versions
from app.db.session import enable_sqlite_foreign_keys
from app.models.day13_replay import D13_SYNTHETIC_TEST_ONLY_KEY, D13ReplayReservation
from tests.migration_test_support import backend_root, repository_alembic_head


def _run_alembic(database_path: Path, *args: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(backend_root() / "alembic.ini"), *args],
        cwd=backend_root(),
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def replay_db(tmp_path: Path) -> tuple[Path, sessionmaker[Session]]:
    db_file = tmp_path / "d31a_replay.sqlite3"
    _run_alembic(db_file, "upgrade", "head")
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    enable_sqlite_foreign_keys(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        ensure_synthetic_demo_versions(session)
        session.commit()
    return db_file, factory


def _clat_scope(
    session: Session,
    *,
    org: str = "org-d31a",
    inst: str = "inst-d31a",
) -> D13ReplayScope:
    _, clat_ver = ensure_synthetic_demo_versions(session)
    return D13ReplayScope(
        organization_id=org,
        institution_id=inst,
        exam_pack_code=CLAT_PACK_CODE,
        exam_version_id=clat_ver.id,
        academic_year="2027",
    )


def _cuet_scope(
    session: Session,
    *,
    org: str = "org-d31a",
    inst: str = "inst-d31a",
) -> D13ReplayScope:
    cuet_ver, _ = ensure_synthetic_demo_versions(session)
    return D13ReplayScope(
        organization_id=org,
        institution_id=inst,
        exam_pack_code=CUET_PACK_CODE,
        exam_version_id=cuet_ver.id,
        academic_year="2026",
    )


def _blueprint(extra: str = "v1") -> dict[str, object]:
    return {"prefix": BLUEPRINT_PREFIX, "demo": extra}


def _fingerprint(scope: D13ReplayScope, *, extra: str = "v1") -> str:
    return build_request_fingerprint(scope, blueprint_snapshot=_blueprint(extra))


def _reserve(
    session: Session,
    scope: D13ReplayScope,
    key: str,
    *,
    extra: str = "v1",
    **kwargs: object,
) -> object:
    return reserve_replay_slot(
        session,
        scope,
        idempotency_key=key,
        blueprint_snapshot=_blueprint(extra),
        **kwargs,
    )


def _publish(
    session: Session,
    scope: D13ReplayScope,
    key: str,
    owner_token: str,
    result_payload: dict[str, object],
    *,
    extra: str = "v1",
    **kwargs: object,
) -> object:
    return publish_replay_result(
        session,
        scope,
        idempotency_key=key,
        blueprint_snapshot=_blueprint(extra),
        owner_token=owner_token,
        result_payload=result_payload,
        **kwargs,
    )


def _read(
    session: Session,
    scope: D13ReplayScope,
    key: str,
    *,
    extra: str = "v1",
    **kwargs: object,
) -> object:
    return read_replay_result(
        session,
        scope,
        idempotency_key=key,
        blueprint_snapshot=_blueprint(extra),
        **kwargs,
    )


def _synthetic_result(checksum_seed: str) -> dict[str, object]:
    opaque_tail = hashlib.sha256(checksum_seed.encode()).hexdigest()[:16]
    return {
        "synthetic_demo_checksum": hashlib.sha256(
            f"demo:{checksum_seed}".encode()
        ).hexdigest(),
        "opaque_plan_ref": f"opl-{opaque_tail}",
    }


def test_migration_upgrade_downgrade_parity(tmp_path: Path) -> None:
    db_file = tmp_path / "migration.sqlite3"
    _run_alembic(db_file, "upgrade", "head")
    with sqlite3.connect(db_file) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='d13_replay_reservations'"
        ).fetchone() is not None
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            repository_alembic_head(),
        )
        connection.execute("PRAGMA foreign_key_check")
    _run_alembic(db_file, "downgrade", "20261109_0018")
    _run_alembic(db_file, "upgrade", "head")


def test_replay_after_session_reopen(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    key = "clat-replay-a"
    with factory() as session:
        scope = _clat_scope(session)
        _fingerprint(scope)
        claim = _reserve(session, scope, key)
        assert claim.state == D13ReservationState.RESERVED
        assert claim.owner_token
        reservation_id = claim.reservation_id
        payload = _synthetic_result("seed-1")
        published = _publish(session, scope, key, claim.owner_token or "", payload)
        session.commit()
    assert published.state == D13ReservationState.REPLAYED
    stored_sum = payload_checksum(published.result_payload or {})
    assert stored_sum is not None
    assert published.payload_sha256 == stored_sum

    with factory() as session:
        scope = _clat_scope(session)
        replay = _read(session, scope, key)
        assert replay.state == D13ReservationState.REPLAYED
        assert replay.reservation_id == reservation_id
        assert replay.payload_sha256 == published.payload_sha256
        assert replay.result_payload == published.result_payload


def test_in_progress_before_complete_conflict_after(
    replay_db: tuple[Path, sessionmaker[Session]],
) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        _fingerprint(scope)
        first = _reserve(session, scope, "k-ip")
        second = _reserve(session, scope, "k-ip")
        session.commit()
    assert first.state == D13ReservationState.RESERVED
    assert second.state == D13ReservationState.IN_PROGRESS

    with factory() as session:
        scope = _clat_scope(session)
        _fingerprint(scope, extra="v2")
        conflict = _reserve(session, scope, "k-ip", extra="v2")
        assert conflict.state == D13ReservationState.CONFLICT


def test_foreign_tenant_no_replay(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    key = "tenant-iso"
    with factory() as session:
        scope_a = _clat_scope(session, org="org-a", inst="inst-a")
        _fingerprint(scope_a)
        claim = _reserve(session, scope_a, key)
        _publish(session, scope_a, key, claim.owner_token or "", _synthetic_result("t1"))
        session.commit()

    with factory() as session:
        scope_b = _clat_scope(session, org="org-b", inst="inst-b")
        _fingerprint(scope_b)
        miss = _read(session, scope_b, key)
        assert miss.state == D13ReservationState.NOT_READY


def test_cross_pack_rejected(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    with factory() as session:
        clat_scope = _clat_scope(session)
        _cuet_scope(session)
        _fingerprint(clat_scope)
        key = "cross-pack"
        _reserve(session, clat_scope, key)
        session.commit()
        wrong_scope = D13ReplayScope(
            organization_id=clat_scope.organization_id,
            institution_id=clat_scope.institution_id,
            exam_pack_code=CUET_PACK_CODE,
            exam_version_id=clat_scope.exam_version_id,
            academic_year=clat_scope.academic_year,
        )
        outcome = _read(session, wrong_scope, key)
        assert outcome.state == D13ReservationState.NOT_READY


def test_thread_race_single_reservation(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    with factory() as session:
        race_scope = _clat_scope(session)
        _fingerprint(race_scope, extra="race")
    barrier = threading.Barrier(2)
    results: list[D13ReservationState] = []
    owners: list[str | None] = []
    lock = threading.Lock()

    def worker() -> None:
        with factory() as session:
            barrier.wait()
            outcome = _reserve(session, race_scope, "race-key", extra="race")
            session.commit()
            with lock:
                results.append(outcome.state)
                owners.append(outcome.owner_token)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)

    assert D13ReservationState.RESERVED in results
    assert D13ReservationState.IN_PROGRESS in results
    reserved_owners = [token for token in owners if token]
    assert len(reserved_owners) == 1

    with factory() as session:
        rows = session.scalars(
            select(D13ReplayReservation).where(
                D13ReplayReservation.idempotency_key_hash == hash_idempotency_key("race-key")
            )
        ).all()
        assert len(rows) == 1


def _process_reserve(db_path: str, result_queue: mp.Queue[str]) -> None:
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    enable_sqlite_foreign_keys(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        _, clat_ver = ensure_synthetic_demo_versions(session)
        scope = D13ReplayScope(
            organization_id="org-mp",
            institution_id="inst-mp",
            exam_pack_code=CLAT_PACK_CODE,
            exam_version_id=clat_ver.id,
            academic_year="2027",
        )
        build_request_fingerprint(
            scope,
            blueprint_snapshot={"prefix": BLUEPRINT_PREFIX, "demo": "mp"},
        )
        outcome = _reserve(session, scope, "mp-race", extra="mp")
        session.commit()
        result_queue.put(outcome.state.value)


def test_multiprocess_race(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    db_file, _ = replay_db
    ctx = mp.get_context("spawn")
    queue: mp.Queue[str] = ctx.Queue()
    processes = [ctx.Process(target=_process_reserve, args=(str(db_file), queue)) for _ in range(2)]
    for process in processes:
        process.start()
    states: list[str] = []
    for _ in processes:
        states.append(queue.get(timeout=90))
    for process in processes:
        process.join(timeout=90)
        assert process.exitcode == 0
    assert states.count(D13ReservationState.RESERVED.value) == 1
    assert states.count(D13ReservationState.IN_PROGRESS.value) == 1


def test_owner_mismatch_on_publish(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        _fingerprint(scope)
        _reserve(session, scope, "owner")
        session.commit()
        bad = _publish(session, scope, "owner", "wrong-owner", _synthetic_result("x"))
        session.commit()
    assert bad.state == D13ReservationState.CONFLICT
    assert D13ReplayIssueCode.PUBLISH_NOT_OWNER in bad.issue_codes


def test_publish_after_complete_different_payload_conflict(
    replay_db: tuple[Path, sessionmaker[Session]],
) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        _fingerprint(scope)
        claim = _reserve(session, scope, "done")
        _publish(session, scope, "done", claim.owner_token or "", _synthetic_result("first"))
        session.commit()
        replay = _read(session, scope, "done")
        assert replay.state == D13ReservationState.REPLAYED
        second = _publish(
            session,
            scope,
            "done",
            claim.owner_token or "",
            _synthetic_result("second"),
        )
        session.commit()
    assert second.state == D13ReservationState.CONFLICT


def test_corrupt_checksum_replay(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        _fingerprint(scope)
        claim = _reserve(session, scope, "corrupt")
        _publish(session, scope, "corrupt", claim.owner_token or "", _synthetic_result("c"))
        row = session.scalar(
            select(D13ReplayReservation).where(D13ReplayReservation.id == claim.reservation_id)
        )
        assert row is not None
        row.payload_sha256 = "0" * 64
        session.commit()
        replay = _read(session, scope, "corrupt")
        assert replay.state == D13ReservationState.CORRUPT
        assert replay.result_payload is None


def test_caller_mutation_does_not_corrupt_store(
    replay_db: tuple[Path, sessionmaker[Session]],
) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        _fingerprint(scope)
        claim = _reserve(session, scope, "mut")
        payload = _synthetic_result("mut")
        published = _publish(session, scope, "mut", claim.owner_token or "", payload)
        session.commit()
        assert published.result_payload is not None
        published.result_payload["synthetic_demo_checksum"] = "f" * 64
        replay = _read(session, scope, "mut")
        assert replay.result_payload is not None
        expected = _synthetic_result("mut")["synthetic_demo_checksum"]
        assert replay.result_payload["synthetic_demo_checksum"] == expected


def test_blank_key_and_missing_tenant(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        _fingerprint(scope)
        blank = _reserve(session, scope, "  ")
        assert blank.state == D13ReservationState.NOT_READY
        bad_scope = D13ReplayScope(
            organization_id="",
            institution_id="inst",
            exam_pack_code=CLAT_PACK_CODE,
            exam_version_id=scope.exam_version_id,
            academic_year="2027",
        )
        tenant = _reserve(session, bad_scope, "k")
        assert tenant.state == D13ReservationState.NOT_READY
        assert D13ReplayIssueCode.MISSING_TENANT in tenant.issue_codes


def test_abort_only_owner(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        _fingerprint(scope)
        claim = _reserve(session, scope, "abort")
        session.commit()
        wrong = abort_reservation(
            session,
            scope,
            idempotency_key="abort",
            blueprint_snapshot=_blueprint(),
            owner_token="not-mine",
        )
        assert wrong.state == D13ReservationState.CONFLICT
        ok = abort_reservation(
            session,
            scope,
            idempotency_key="abort",
            blueprint_snapshot=_blueprint(),
            owner_token=claim.owner_token or "",
        )
        session.commit()
        assert ok.state == D13ReservationState.NOT_READY
        again = _read(session, scope, "abort")
        assert again.state == D13ReservationState.NOT_READY


def test_postgres_compile_includes_d13_table() -> None:
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable

    from app.db.base import Base

    table = Base.metadata.tables["d13_replay_reservations"]
    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert "d13_replay_reservations" in ddl
    assert "uq_d13_replay_reservation_scope_key" in ddl


def test_result_always_tagged_synthetic(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        _fingerprint(scope)
        claim = _reserve(session, scope, "tag")
        published = _publish(
            session,
            scope,
            "tag",
            claim.owner_token or "",
            _synthetic_result("z"),
        )
        session.commit()
        assert published.result_payload is not None
        assert published.result_payload[D13_SYNTHETIC_TEST_ONLY_KEY] is True


def test_replay_after_engine_dispose(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    db_file, factory = replay_db
    key = "engine-dispose"
    reservation_id: str | None = None
    published_checksum: str | None = None
    with factory() as session:
        scope = _clat_scope(session)
        claim = _reserve(session, scope, key)
        reservation_id = claim.reservation_id
        published = _publish(
            session,
            scope,
            key,
            claim.owner_token or "",
            _synthetic_result("dispose"),
        )
        session.commit()
        published_checksum = published.payload_sha256
    bind = factory.kw["bind"]
    assert bind is not None
    bind.dispose()
    new_engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    enable_sqlite_foreign_keys(new_engine)
    new_factory = sessionmaker(bind=new_engine, autoflush=False, expire_on_commit=False)
    with new_factory() as session:
        scope = _clat_scope(session)
        replay = confirmed_read_after_commit(
            session,
            scope,
            idempotency_key=key,
            blueprint_snapshot=_blueprint(),
        )
        assert replay.state == D13ReservationState.REPLAYED
        assert replay.reservation_id == reservation_id
        assert replay.payload_sha256 == published_checksum


def test_asserted_fingerprint_mismatch(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        forged = "f" * 64
        bad = _reserve(session, scope, "forge", asserted_fingerprint=forged)
        assert bad.state == D13ReservationState.CONFLICT
        assert D13ReplayIssueCode.FINGERPRINT_ASSERTED_MISMATCH in bad.issue_codes


def test_blueprint_change_not_hidden_by_stale_hash(
    replay_db: tuple[Path, sessionmaker[Session]],
) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        claim = _reserve(session, scope, "bp", extra="b1")
        session.commit()
        conflict = _read(session, scope, "bp", extra="b2")
        assert conflict.state == D13ReservationState.CONFLICT
        assert claim.request_fingerprint == _fingerprint(scope, extra="b1")
        assert claim.request_fingerprint != _fingerprint(scope, extra="b2")


def test_forbidden_result_schema(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        claim = _reserve(session, scope, "forbid")
        bad = _publish(
            session,
            scope,
            "forbid",
            claim.owner_token or "",
            {
                "synthetic_demo_checksum": "a" * 64,
                "opaque_plan_ref": "opl-abcdefghijklmnop",
                "question_text": "leak",
            },
        )
        assert bad.state == D13ReservationState.NOT_READY
        assert D13ReplayIssueCode.RESULT_SCHEMA_VIOLATION in bad.issue_codes


def test_exam_year_mismatch_on_scope(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        wrong_year = D13ReplayScope(
            organization_id=scope.organization_id,
            institution_id=scope.institution_id,
            exam_pack_code=scope.exam_pack_code,
            exam_version_id=scope.exam_version_id,
            academic_year="2026",
        )
        outcome = _reserve(session, wrong_year, "year-bad")
        assert outcome.state == D13ReservationState.NOT_READY
        assert D13ReplayIssueCode.EXAM_YEAR_MISMATCH in outcome.issue_codes


def test_pending_row_with_null_owner_is_corrupt(
    replay_db: tuple[Path, sessionmaker[Session]],
) -> None:
    db_file, factory = replay_db
    row_id: str | None = None
    with factory() as session:
        scope = _clat_scope(session)
        claim = _reserve(session, scope, "pending-corrupt")
        row_id = claim.reservation_id
        session.commit()
    with sqlite3.connect(db_file) as connection:
        connection.execute(
            "UPDATE d13_replay_reservations SET owner_token = NULL WHERE id = ?",
            (row_id,),
        )
        connection.commit()
    with factory() as session:
        scope = _clat_scope(session)
        replay = _read(session, scope, "pending-corrupt")
        assert replay.state == D13ReservationState.CORRUPT
        assert replay.result_payload is None


def test_concurrent_publish_single_winner(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    db_file, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        claim = _reserve(session, scope, "pub-race")
        owner = claim.owner_token or ""
        session.commit()
    barrier = threading.Barrier(2)
    committed_replayed: list[bool] = []
    lock = threading.Lock()

    def worker(seed: str) -> None:
        with factory() as session:
            scope = _clat_scope(session)
            barrier.wait()
            outcome = _publish(session, scope, "pub-race", owner, _synthetic_result(seed))
            committed = False
            try:
                session.commit()
                if outcome.state == D13ReservationState.REPLAYED and outcome.payload_sha256:
                    with factory() as verify_session:
                        replay = confirmed_read_after_commit(
                            verify_session,
                            scope,
                            idempotency_key="pub-race",
                            blueprint_snapshot=_blueprint(),
                        )
                        committed = (
                            replay.state == D13ReservationState.REPLAYED
                            and replay.payload_sha256 == outcome.payload_sha256
                        )
            except Exception:
                session.rollback()
            with lock:
                committed_replayed.append(committed)

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)
    assert committed_replayed.count(True) == 1

    verify_engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    enable_sqlite_foreign_keys(verify_engine)
    verify_factory = sessionmaker(bind=verify_engine, autoflush=False, expire_on_commit=False)
    with verify_factory() as session:
        scope = _clat_scope(session)
        replay = confirmed_read_after_commit(
            session,
            scope,
            idempotency_key="pub-race",
            blueprint_snapshot=_blueprint(),
        )
        assert replay.state == D13ReservationState.REPLAYED
        assert replay.result_payload is not None


def test_abort_vs_publish_cas(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        claim = _reserve(session, scope, "abort-pub")
        owner = claim.owner_token or ""
        transition_to_in_progress(
            session,
            scope,
            idempotency_key="abort-pub",
            blueprint_snapshot=_blueprint(),
            owner_token=owner,
        )
        session.commit()
    with factory() as session:
        scope = _clat_scope(session)
        aborted = abort_reservation(
            session,
            scope,
            idempotency_key="abort-pub",
            blueprint_snapshot=_blueprint(),
            owner_token=owner,
        )
        session.commit()
        assert aborted.state == D13ReservationState.NOT_READY
        blocked = _publish(session, scope, "abort-pub", owner, _synthetic_result("late"))
        assert blocked.state == D13ReservationState.NOT_READY


def test_confirmed_read_rejects_uncommitted_transaction(
    replay_db: tuple[Path, sessionmaker[Session]],
) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        claim = _reserve(session, scope, "uncommit")
        _publish(session, scope, "uncommit", claim.owner_token or "", _synthetic_result("u"))
        early = confirmed_read_after_commit(
            session,
            scope,
            idempotency_key="uncommit",
            blueprint_snapshot=_blueprint(),
        )
        assert early.state != D13ReservationState.REPLAYED
        assert early.result_payload is None
        session.rollback()
        replay = _read(session, scope, "uncommit")
        assert replay.state == D13ReservationState.NOT_READY


def test_corrupt_pending_metadata_blocks_publish(
    replay_db: tuple[Path, sessionmaker[Session]],
) -> None:
    db_file, factory = replay_db
    row_id: str | None = None
    owner: str = ""
    with factory() as session:
        scope = _clat_scope(session)
        claim = _reserve(session, scope, "meta-corrupt")
        row_id = claim.reservation_id
        owner = claim.owner_token or ""
        session.commit()
    with sqlite3.connect(db_file) as connection:
        connection.execute(
            "UPDATE d13_replay_reservations SET metadata_json = ? WHERE id = ?",
            (json.dumps({}), row_id),
        )
        connection.commit()
    with factory() as session:
        scope = _clat_scope(session)
        blocked = _publish(session, scope, "meta-corrupt", owner, _synthetic_result("bad"))
        session.commit()
        assert blocked.state == D13ReservationState.CORRUPT
        row = session.get(D13ReplayReservation, row_id)
        assert row is not None
        assert row.reservation_state in {
            D13ReservationState.RESERVED.value,
            D13ReservationState.IN_PROGRESS.value,
        }


def test_replayed_json_array_is_corrupt(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    db_file, factory = replay_db
    row_id: str | None = None
    with factory() as session:
        scope = _clat_scope(session)
        claim = _reserve(session, scope, "json-arr")
        _publish(session, scope, "json-arr", claim.owner_token or "", _synthetic_result("arr"))
        row_id = claim.reservation_id
        session.commit()
    with sqlite3.connect(db_file) as connection:
        connection.execute(
            "UPDATE d13_replay_reservations SET reservation_state = 'replayed', "
            "owner_token = NULL, result_json = ?, payload_sha256 = ?, "
            "result_snapshot_version = 'd13-replay-snapshot@v3' WHERE id = ?",
            (json.dumps([]), "0" * 64, row_id),
        )
        connection.commit()
    with factory() as session:
        scope = _clat_scope(session)
        replay = _read(session, scope, "json-arr")
        assert replay.state == D13ReservationState.CORRUPT
        assert replay.result_payload is None


def test_blueprint_nan_rejected(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        fp, issue = derive_request_fingerprint(
            scope,
            blueprint_snapshot={"prefix": BLUEPRINT_PREFIX, "bad": float("nan")},
        )
        assert fp is None
        assert issue == D13ReplayIssueCode.BLUEPRINT_INVALID


def test_opaque_prose_rejected_on_publish(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        claim = _reserve(session, scope, "prose")
        bad = _publish(
            session,
            scope,
            "prose",
            claim.owner_token or "",
            {
                "synthetic_demo_checksum": "a" * 64,
                "opaque_plan_ref": "this is not a token but question text hidden",
            },
        )
        assert bad.state == D13ReservationState.NOT_READY
        assert D13ReplayIssueCode.RESULT_SCHEMA_VIOLATION in bad.issue_codes


def test_inactive_pack_blocks_replay_after_reserve(
    replay_db: tuple[Path, sessionmaker[Session]],
) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        from app.models.examination import ExamPack, ExamVersion

        exam_version = session.get(ExamVersion, scope.exam_version_id)
        assert exam_version is not None
        real_pack = session.get(ExamPack, exam_version.exam_pack_id)
        assert real_pack is not None
        claim = _reserve(session, scope, "pack-off")
        session.commit()
        real_pack.active = False
        session.commit()
        blocked = _publish(
            session,
            scope,
            "pack-off",
            claim.owner_token or "",
            _synthetic_result("off"),
        )
        assert blocked.state == D13ReservationState.NOT_READY
        assert D13ReplayIssueCode.EXAM_VERSION_INVALID in blocked.issue_codes
        real_pack.active = True
        session.commit()


def test_postgres_compile_includes_synthetic_column() -> None:
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable

    from app.db.base import Base

    table = Base.metadata.tables["d13_replay_reservations"]
    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert "synthetic_test_only" in ddl
    assert "ck_d13_replay_synthetic_marker" in ddl