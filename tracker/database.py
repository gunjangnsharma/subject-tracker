"""SQLAlchemy engine and session management.

Kept separate from models and Flask so any layer can obtain a session
without importing web concerns. A scoped session gives us one session per
request/thread that we tidy up in the app's teardown hook.

SQLite tuning lives here too (see ``_TUNING_PRAGMAS``). The defaults are poor for
a small multi-user web app on slow storage — most importantly, the default
rollback journal makes a writer take an **exclusive lock on the whole database
file**, so any write blocks every concurrent read and the whole UI appears to
freeze. WAL fixes that; the rest cuts per-commit fsync cost.
"""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


#: PRAGMAs applied to every SQLite connection, in order. Each entry is
#: (pragma, value, why).
_TUNING_PRAGMAS: tuple[tuple[str, str, str], ...] = (
    # Readers never block on the writer (and vice versa). Without this a single
    # DELETE holds an EXCLUSIVE lock on the file and every other request stalls
    # behind it — the "whole UI hangs on delete" symptom. Persistent: stored in
    # the database file, so setting it repeatedly is a cheap no-op.
    ("journal_mode", "WAL", "concurrent reads during writes"),
    # Don't fsync on every commit; the WAL still guarantees crash-consistency,
    # you only risk losing the last few commits on a *power* loss (not a crash).
    # On SD cards / slow storage this is the single biggest win: measured
    # ~13.9 ms/commit at FULL vs ~0.05 ms at NORMAL+WAL.
    ("synchronous", "NORMAL", "avoid an fsync per commit"),
    # Wait (rather than erroring) if another connection holds the write lock.
    # Milliseconds. Prevents spurious "database is locked" under concurrency.
    ("busy_timeout", "5000", "queue behind a writer instead of failing"),
    # Honour the ondelete="CASCADE" foreign keys. SQLite disables FK enforcement
    # by default, so DB-level cascades never fired; the ORM was doing all the
    # cascading in Python.
    ("foreign_keys", "ON", "enforce FK constraints / DB-level cascades"),
    # ~8 MB page cache (negative = KiB) instead of the 2 MB default: fewer reads
    # from slow storage. Comfortable even on a 1 GB Pi.
    ("cache_size", "-8000", "keep more pages in RAM"),
    # Temp b-trees for ORDER BY / joins in memory rather than on the SD card.
    ("temp_store", "MEMORY", "no temp files on slow storage"),
)


class Database:
    """Owns the engine + session factory for one database URL."""

    def __init__(self, url: str) -> None:
        # check_same_thread=False lets the Flask dev server share the
        # in-process SQLite connection across threads safely for our use.
        is_sqlite = url.startswith("sqlite")
        connect_args = {"check_same_thread": False} if is_sqlite else {}
        self.engine = create_engine(url, future=True, connect_args=connect_args)
        self.session_factory = sessionmaker(bind=self.engine, future=True, expire_on_commit=False)
        self.Session = scoped_session(self.session_factory)
        if is_sqlite:
            # An in-memory database has no file to lock and no storage to sync,
            # so the tuning is pointless there (and WAL is unsupported).
            self._tune_sqlite(persistent=":memory:" not in url)

    def _tune_sqlite(self, persistent: bool) -> None:
        """Apply _TUNING_PRAGMAS to every new connection in this pool."""

        @event.listens_for(self.engine, "connect")
        def _set_pragmas(dbapi_connection, _record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                for pragma, value, _why in _TUNING_PRAGMAS:
                    if pragma == "journal_mode" and not persistent:
                        continue
                    cursor.execute(f"PRAGMA {pragma}={value}")
            finally:
                cursor.close()

    def create_all(self) -> None:
        # Import models so they are registered on Base before create_all.
        from tracker import models  # noqa: F401
        from tracker.schema import ensure_columns, ensure_indexes

        Base.metadata.create_all(self.engine)
        # create_all only creates *missing tables*; it never alters an existing
        # one, nor adds indexes to it. Reconcile both so a database written by an
        # older version stays queryable *and* keeps its indexes. See schema.py.
        added = ensure_columns(self.engine)
        ensure_indexes(self.engine)
        return added

    def remove(self) -> None:
        """Dispose of the current scoped session (call on teardown)."""
        self.Session.remove()
