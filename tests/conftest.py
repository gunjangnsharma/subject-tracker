"""Shared pytest fixtures.

Each test gets a fresh in-memory SQLite database (a new engine per app), so
tests are isolated and never touch the on-disk dev database.
"""

from __future__ import annotations

import pytest

from tracker import create_app
from tracker.config import TestConfig


@pytest.fixture
def app():
    application = create_app(TestConfig)
    yield application
    application.database.remove()  # type: ignore[attr-defined]


@pytest.fixture
def session(app):
    """A DB session bound to the test app's in-memory database."""
    db = app.database  # type: ignore[attr-defined]
    sess = db.Session()
    yield sess
    db.remove()


@pytest.fixture
def client(app):
    return app.test_client()
