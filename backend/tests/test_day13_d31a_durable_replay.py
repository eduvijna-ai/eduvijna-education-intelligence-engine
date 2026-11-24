from __future__ import annotations

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
    hash_idempotency_key,
    payload_checksum,
    publish_replay_result,
    read_replay_result,
    reserve_replay_slot,
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


def _fingerprint(scope: D13ReplayScope, *, extra: str = "v1") -> str:
    return build_request_fingerprint(
        scope,
        blueprint_snapshot={"prefix": BLUEPRINT_PREFIX, "demo": extra},
    )


def _synthetic_result(checksum_seed: str) -> dict[str, object]:
    return {
        "synthetic_demo_checksum": checksum_seed,
        "opaque_plan_ref": f"plan-{checksum_seed}",
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
        fp = _fingerprint(scope)
        claim = reserve_replay_slot(session, scope, idempotency_key=key, request_fingerprint=fp)
        assert claim.state == D13ReservationState.RESERVED
        assert claim.owner_token
        reservation_id = claim.reservation_id
        payload = _synthetic_result("seed-1")
        published = publish_replay_result(
            session,
            scope,
            idempotency_key=key,
            request_fingerprint=fp,
            owner_token=claim.owner_token,
            result_payload=payload,
        )
        session.commit()
    assert published.state == D13ReservationState.REPLAYED
    assert published.payload_sha256 == payload_checksum(published.result_payload or {})

    with factory() as session:
        scope = _clat_scope(session)
        fp = _fingerprint(scope)
        replay = read_replay_result(session, scope, idempotency_key=key, request_fingerprint=fp)
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
        fp = _fingerprint(scope)
        first = reserve_replay_slot(session, scope, idempotency_key="k-ip", request_fingerprint=fp)
        second = reserve_replay_slot(session, scope, idempotency_key="k-ip", request_fingerprint=fp)
        session.commit()
    assert first.state == D13ReservationState.RESERVED
    assert second.state == D13ReservationState.IN_PROGRESS

    with factory() as session:
        scope = _clat_scope(session)
        fp2 = _fingerprint(scope, extra="v2")
        conflict = reserve_replay_slot(
            session,
            scope,
            idempotency_key="k-ip",
            request_fingerprint=fp2,
        )
        assert conflict.state == D13ReservationState.CONFLICT


def test_foreign_tenant_no_replay(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    key = "tenant-iso"
    with factory() as session:
        scope_a = _clat_scope(session, org="org-a", inst="inst-a")
        fp = _fingerprint(scope_a)
        claim = reserve_replay_slot(session, scope_a, idempotency_key=key, request_fingerprint=fp)
        publish_replay_result(
            session,
            scope_a,
            idempotency_key=key,
            request_fingerprint=fp,
            owner_token=claim.owner_token or "",
            result_payload=_synthetic_result("t1"),
        )
        session.commit()

    with factory() as session:
        scope_b = _clat_scope(session, org="org-b", inst="inst-b")
        fp_b = _fingerprint(scope_b)
        miss = read_replay_result(session, scope_b, idempotency_key=key, request_fingerprint=fp_b)
        assert miss.state == D13ReservationState.NOT_READY


def test_cross_pack_rejected(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    with factory() as session:
        clat_scope = _clat_scope(session)
        _cuet_scope(session)
        fp_clat = _fingerprint(clat_scope)
        key = "cross-pack"
        reserve_replay_slot(session, clat_scope, idempotency_key=key, request_fingerprint=fp_clat)
        session.commit()
        wrong_scope = D13ReplayScope(
            organization_id=clat_scope.organization_id,
            institution_id=clat_scope.institution_id,
            exam_pack_code=CUET_PACK_CODE,
            exam_version_id=clat_scope.exam_version_id,
            academic_year=clat_scope.academic_year,
        )
        outcome = read_replay_result(
            session,
            wrong_scope,
            idempotency_key=key,
            request_fingerprint=fp_clat,
        )
        assert outcome.state == D13ReservationState.NOT_READY


def test_thread_race_single_reservation(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    with factory() as session:
        race_scope = _clat_scope(session)
        race_fp = _fingerprint(race_scope, extra="race")
    barrier = threading.Barrier(2)
    results: list[D13ReservationState] = []
    owners: list[str | None] = []
    lock = threading.Lock()

    def worker() -> None:
        with factory() as session:
            barrier.wait()
            outcome = reserve_replay_slot(
                session,
                race_scope,
                idempotency_key="race-key",
                request_fingerprint=race_fp,
            )
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
        fp = build_request_fingerprint(
            scope,
            blueprint_snapshot={"prefix": BLUEPRINT_PREFIX, "demo": "mp"},
        )
        outcome = reserve_replay_slot(
            session,
            scope,
            idempotency_key="mp-race",
            request_fingerprint=fp,
        )
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
        fp = _fingerprint(scope)
        reserve_replay_slot(session, scope, idempotency_key="owner", request_fingerprint=fp)
        session.commit()
        bad = publish_replay_result(
            session,
            scope,
            idempotency_key="owner",
            request_fingerprint=fp,
            owner_token="wrong-owner",
            result_payload=_synthetic_result("x"),
        )
        session.commit()
    assert bad.state == D13ReservationState.CONFLICT
    assert D13ReplayIssueCode.PUBLISH_NOT_OWNER in bad.issue_codes


def test_publish_after_complete_different_payload_conflict(
    replay_db: tuple[Path, sessionmaker[Session]],
) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        fp = _fingerprint(scope)
        claim = reserve_replay_slot(session, scope, idempotency_key="done", request_fingerprint=fp)
        publish_replay_result(
            session,
            scope,
            idempotency_key="done",
            request_fingerprint=fp,
            owner_token=claim.owner_token or "",
            result_payload=_synthetic_result("first"),
        )
        session.commit()
        replay = read_replay_result(session, scope, idempotency_key="done", request_fingerprint=fp)
        assert replay.state == D13ReservationState.REPLAYED
        second = publish_replay_result(
            session,
            scope,
            idempotency_key="done",
            request_fingerprint=fp,
            owner_token=claim.owner_token or "",
            result_payload=_synthetic_result("second"),
        )
        session.commit()
    assert second.state == D13ReservationState.CONFLICT


def test_corrupt_checksum_replay(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        fp = _fingerprint(scope)
        claim = reserve_replay_slot(
            session,
            scope,
            idempotency_key="corrupt",
            request_fingerprint=fp,
        )
        publish_replay_result(
            session,
            scope,
            idempotency_key="corrupt",
            request_fingerprint=fp,
            owner_token=claim.owner_token or "",
            result_payload=_synthetic_result("c"),
        )
        row = session.scalar(
            select(D13ReplayReservation).where(D13ReplayReservation.id == claim.reservation_id)
        )
        assert row is not None
        row.payload_sha256 = "0" * 64
        session.commit()
        replay = read_replay_result(
            session,
            scope,
            idempotency_key="corrupt",
            request_fingerprint=fp,
        )
        assert replay.state == D13ReservationState.CORRUPT
        assert replay.result_payload is None


def test_caller_mutation_does_not_corrupt_store(
    replay_db: tuple[Path, sessionmaker[Session]],
) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        fp = _fingerprint(scope)
        claim = reserve_replay_slot(session, scope, idempotency_key="mut", request_fingerprint=fp)
        payload = _synthetic_result("mut")
        published = publish_replay_result(
            session,
            scope,
            idempotency_key="mut",
            request_fingerprint=fp,
            owner_token=claim.owner_token or "",
            result_payload=payload,
        )
        session.commit()
        assert published.result_payload is not None
        published.result_payload["synthetic_demo_checksum"] = "tampered"
        replay = read_replay_result(session, scope, idempotency_key="mut", request_fingerprint=fp)
        assert replay.result_payload is not None
        assert replay.result_payload["synthetic_demo_checksum"] == "mut"


def test_blank_key_and_missing_tenant(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        fp = _fingerprint(scope)
        blank = reserve_replay_slot(session, scope, idempotency_key="  ", request_fingerprint=fp)
        assert blank.state == D13ReservationState.NOT_READY
        bad_scope = D13ReplayScope(
            organization_id="",
            institution_id="inst",
            exam_pack_code=CLAT_PACK_CODE,
            exam_version_id=scope.exam_version_id,
            academic_year="2027",
        )
        tenant = reserve_replay_slot(
            session,
            bad_scope,
            idempotency_key="k",
            request_fingerprint=fp,
        )
        assert tenant.state == D13ReservationState.NOT_READY
        assert D13ReplayIssueCode.MISSING_TENANT in tenant.issue_codes


def test_abort_only_owner(replay_db: tuple[Path, sessionmaker[Session]]) -> None:
    _, factory = replay_db
    with factory() as session:
        scope = _clat_scope(session)
        fp = _fingerprint(scope)
        claim = reserve_replay_slot(session, scope, idempotency_key="abort", request_fingerprint=fp)
        session.commit()
        wrong = abort_reservation(
            session,
            scope,
            idempotency_key="abort",
            request_fingerprint=fp,
            owner_token="not-mine",
        )
        assert wrong.state == D13ReservationState.CONFLICT
        ok = abort_reservation(
            session,
            scope,
            idempotency_key="abort",
            request_fingerprint=fp,
            owner_token=claim.owner_token or "",
        )
        session.commit()
        assert ok.state == D13ReservationState.NOT_READY
        again = read_replay_result(session, scope, idempotency_key="abort", request_fingerprint=fp)
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
        fp = _fingerprint(scope)
        claim = reserve_replay_slot(session, scope, idempotency_key="tag", request_fingerprint=fp)
        published = publish_replay_result(
            session,
            scope,
            idempotency_key="tag",
            request_fingerprint=fp,
            owner_token=claim.owner_token or "",
            result_payload={"checksum": "z"},
        )
        session.commit()
        assert published.result_payload is not None
        assert published.result_payload[D13_SYNTHETIC_TEST_ONLY_KEY] is True