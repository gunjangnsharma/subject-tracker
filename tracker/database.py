"""SQLAlchemy engine and session management.

Kept separate from models and Flask so any layer can obtain a session
without importing web concerns. A scoped session gives us one session per
request/thread that we tidy up in the app's teardown hook.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class Database:
    """Owns the engine + session factory for one database URL."""

    def __init__(self, url: str) -> None:
        # check_same_thread=False lets the Flask dev server share the
        # in-process SQLite connection across threads safely for our use.
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, future=True, connect_args=connect_args)
        self.session_factory = sessionmaker(bind=self.engine, future=True, expire_on_commit=False)
        self.Session = scoped_session(self.session_factory)

    def create_all(self) -> None:
        # Import models so they are registered on Base before create_all.
        from tracker import models  # noqa: F401
        from tracker.schema import ensure_columns

        Base.metadata.create_all(self.engine)
        # create_all only creates *missing tables*; it never alters an existing
        # one. Reconcile columns added after a table was first created, so a
        # database written by an older version stays queryable. See schema.py.
        return ensure_columns(self.engine)

    def remove(self) -> None:
        """Dispose of the current scoped session (call on teardown)."""
        self.Session.remove()

    def remove(self) -> None:
        """Dispose of the current scoped session (call on teardown)."""
        self.Session.remove()
