"""Application configuration objects."""

from __future__ import annotations

import os


class Config:
    """Base config. Override attributes via env vars where useful."""

    # Default on-disk SQLite database, sitting next to the package.
    DATABASE_URL = os.environ.get(
        "SUBJECT_TRACKER_DB",
        "sqlite:///" + os.path.join(os.getcwd(), "subject_tracker.db"),
    )
    SECRET_KEY = os.environ.get("SUBJECT_TRACKER_SECRET", "dev-secret-change-me")


class TestConfig(Config):
    """Config for tests: fast, isolated, in-memory database."""

    DATABASE_URL = "sqlite:///:memory:"
    TESTING = True
