"""SQLite tuning and index reconciliation (the Raspberry Pi performance work).

Two distinct problems are covered here:

1. **The UI froze during any write.** SQLite's default rollback journal makes a
   writer take an EXCLUSIVE lock on the whole database file, so every concurrent
   read blocks behind it. WAL lets readers and the writer proceed together.
2. **Everything was slow.** `synchronous=FULL` fsyncs on every commit (brutal on
   an SD card), and SQLite does not index foreign keys automatically, so every
   ownership check and join was a full table scan.

These tests assert the configuration is actually applied — including to a
database created before the indexes existed, which is the upgrade path for a
already-deployed Pi.
"""

from __future__ import annotations

import threading
import time

import pytest
from sqlalchemy import inspect, text

from tracker.database import _TUNING_PRAGMAS, Database
from tracker.schema import ensure_indexes

# Indexes every deployment should end up with. Names come from models.py.
EXPECTED_INDEXES = {
    "ix_subjects_user_id",
    "ix_modules_subject_id",
    "ix_chapters_module_id_position",
    "ix_plan_assignments_planned_date",
    "ix_plan_assignments_chapter_id",
    "ix_progress_events_occurred_on",
    "ix_progress_events_chapter_id",
}


def pragma(db: Database, name: str):
    with db.engine.connect() as conn:
        return conn.execute(text(f"PRAGMA {name}")).scalar()


@pytest.fixture
def file_db(tmp_path):
    """A real on-disk database (WAL and fsync only mean something with a file)."""
    db = Database(f"sqlite:///{tmp_path/'perf.db'}")
    db.create_all()
    yield db
    db.remove()


# --- Pragmas ----------------------------------------------------------------

def test_wal_is_enabled(file_db):
    """WAL is the fix for 'the whole UI hangs while anything is written'."""
    assert pragma(file_db, "journal_mode") == "wal"


def test_synchronous_is_normal(file_db):
    """NORMAL (1) instead of FULL (2): no fsync per commit. Big win on SD cards."""
    assert pragma(file_db, "synchronous") == 1


def test_busy_timeout_is_set(file_db):
    """Wait for a busy writer instead of raising 'database is locked'."""
    assert pragma(file_db, "busy_timeout") == 5000


def test_foreign_keys_are_enforced(file_db):
    """ondelete="CASCADE" is inert unless FK enforcement is on."""
    assert pragma(file_db, "foreign_keys") == 1


def test_cache_and_temp_store_tuned(file_db):
    assert pragma(file_db, "cache_size") == -8000     # ~8 MB, negative = KiB
    assert pragma(file_db, "temp_store") == 2         # 2 = MEMORY


def test_pragmas_apply_to_every_pooled_connection(file_db):
    """The PRAGMAs are set on connect, so a second connection is tuned too."""
    with file_db.engine.connect() as first, file_db.engine.connect() as second:
        for conn in (first, second):
            assert conn.execute(text("PRAGMA synchronous")).scalar() == 1
            assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_memory_database_skips_wal_but_keeps_the_rest(tmp_path):
    """An in-memory DB has no file to lock; WAL is unsupported, tuning still applies."""
    db = Database("sqlite:///:memory:")
    db.create_all()
    assert pragma(db, "journal_mode") == "memory"      # not wal, and no error
    assert pragma(db, "foreign_keys") == 1
    db.remove()


def test_tuning_pragmas_are_documented():
    """Each pragma carries a 'why' so the next reader knows what it buys."""
    for name, value, why in _TUNING_PRAGMAS:
        assert name and value and why, f"{name} is missing its rationale"


# --- Indexes ----------------------------------------------------------------

def test_fresh_database_has_every_index(file_db):
    inspector = inspect(file_db.engine)
    found = {
        index["name"]
        for table in inspector.get_table_names()
        for index in inspector.get_indexes(table)
    }
    assert EXPECTED_INDEXES <= found


def test_existing_database_gains_missing_indexes(tmp_path):
    """The upgrade path for an already-deployed Pi: indexes appear on restart.

    create_all() only builds indexes for tables it creates, so a database from
    before this change keeps scanning. ensure_indexes backfills them.
    """
    path = tmp_path / "legacy.db"
    db = Database(f"sqlite:///{path}")
    db.create_all()

    # Simulate the pre-index deployment by dropping them all back off.
    with db.engine.begin() as conn:
        for name in EXPECTED_INDEXES:
            conn.execute(text(f"DROP INDEX IF EXISTS {name}"))
    remaining = {
        index["name"]
        for table in inspect(db.engine).get_table_names()
        for index in inspect(db.engine).get_indexes(table)
    }
    assert not (EXPECTED_INDEXES & remaining)

    created = ensure_indexes(db.engine)

    assert set(created) == EXPECTED_INDEXES
    found = {
        index["name"]
        for table in inspect(db.engine).get_table_names()
        for index in inspect(db.engine).get_indexes(table)
    }
    assert EXPECTED_INDEXES <= found
    db.remove()


def test_ensure_indexes_is_idempotent(file_db):
    assert ensure_indexes(file_db.engine) == []      # already complete
    assert ensure_indexes(file_db.engine) == []      # and still nothing to do


def test_queries_use_indexes_not_table_scans(file_db):
    """The planner picks an index for the app's hot lookups."""
    hot_queries = [
        "SELECT * FROM subjects WHERE user_id = 1",
        "SELECT * FROM chapters WHERE module_id = 1 ORDER BY position, id",
        "SELECT * FROM plan_assignments WHERE planned_date < '2026-01-01'",
        "SELECT * FROM progress_events WHERE occurred_on = '2026-01-01'",
    ]
    with file_db.engine.connect() as conn:
        for query in hot_queries:
            plan = " ".join(
                str(row[3]) for row in conn.execute(text("EXPLAIN QUERY PLAN " + query))
            )
            assert "USING INDEX" in plan, f"no index used for: {query}\n  plan: {plan}"


# --- The actual symptom: concurrency ----------------------------------------

def test_a_read_is_not_blocked_by_an_in_flight_write(tmp_path):
    """The regression test for 'deleting hangs the whole UI'.

    Under the old rollback journal an uncommitted write held an EXCLUSIVE lock
    and this read raised 'database is locked'. Under WAL it returns immediately.
    """
    db = Database(f"sqlite:///{tmp_path/'concurrent.db'}")
    db.create_all()
    with db.engine.begin() as seed:
        seed.execute(text("INSERT INTO users (username, password_hash, role) "
                          "VALUES ('a', 'h', 'user')"))

    writer = db.engine.connect()
    writer.execute(text("BEGIN EXCLUSIVE"))
    writer.execute(text("INSERT INTO users (username, password_hash, role) "
                        "VALUES ('b', 'h', 'user')"))
    try:
        started = time.perf_counter()
        with db.engine.connect() as reader:
            count = reader.execute(text("SELECT COUNT(*) FROM users")).scalar()
        elapsed = time.perf_counter() - started
        assert count == 1                 # sees the pre-write state, does not block
        assert elapsed < 1.0, f"read waited {elapsed:.2f}s on the writer"
    finally:
        writer.rollback()
        writer.close()
    db.remove()


def test_concurrent_writes_queue_instead_of_failing(tmp_path):
    """busy_timeout makes a second writer wait its turn rather than erroring."""
    db = Database(f"sqlite:///{tmp_path/'queue.db'}")
    db.create_all()

    errors: list[Exception] = []

    def insert(name: str) -> None:
        try:
            with db.engine.begin() as conn:
                conn.execute(text("INSERT INTO users (username, password_hash, role) "
                                  "VALUES (:n, 'h', 'user')"), {"n": name})
        except Exception as exc:          # pragma: no cover - the failure we guard against
            errors.append(exc)

    threads = [threading.Thread(target=insert, args=(f"user{i}",)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, f"concurrent writes failed: {errors}"
    with db.engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM users")).scalar() == 8
    db.remove()


def test_page_loads_while_a_delete_is_in_flight(app, monkeypatch, tmp_path):
    """End-to-end: a request still renders while another thread writes."""
    from tracker.services.auth_service import AuthService
    from tracker.services.subject_service import SubjectService

    db = Database(f"sqlite:///{tmp_path/'app.db'}")
    db.create_all()
    session = db.Session()
    user = AuthService(session).register("perf", "secret123")
    service = SubjectService(session, user.id)
    subject = service.add_subject("Doomed")
    module = service.add_module(subject.id, "Module")
    for i in range(20):
        service.add_chapter(module.id, f"Chapter {i}", "video", 60)
    db.remove()

    timings: dict[str, float] = {}

    def delete_subject() -> None:
        s = db.Session()
        started = time.perf_counter()
        SubjectService(s, user.id).delete_subject(subject.id)
        timings["write"] = time.perf_counter() - started
        db.remove()

    def read_subjects() -> None:
        s = db.Session()
        started = time.perf_counter()
        SubjectService(s, user.id).list_subjects()
        timings["read"] = time.perf_counter() - started
        db.remove()

    writer = threading.Thread(target=delete_subject)
    reader = threading.Thread(target=read_subjects)
    writer.start()
    reader.start()
    writer.join()
    reader.join()

    assert timings["read"] < 1.0, f"read took {timings['read']:.2f}s during a delete"
