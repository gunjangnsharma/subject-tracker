"""Shared pytest fixtures.

Each test gets a fresh in-memory SQLite database (a new engine per app), so
tests are isolated and never touch the on-disk dev database.
"""

from __future__ import annotations

import pytest

from tracker import create_app
from tracker.config import TestConfig
from tracker.services.auth_service import AuthService


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
def user_id(session):
    """A registered non-admin user; returns its id for scoping services."""
    return AuthService(session).register("tester", "secret123").id


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """A test client with a logged-in user (registered via the app)."""
    client.post(
        "/register",
        data={"username": "tester", "password": "secret123"},
        follow_redirects=True,
    )
    return client
