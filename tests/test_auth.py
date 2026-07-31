"""Tests for registration, login/logout and access control."""

import pytest

from tracker.services.auth_service import AuthService


# --- Service-level -------------------------------------------------------
def test_register_hashes_password(session):
    user = AuthService(session).register("alice", "secret123")
    assert user.password_hash != "secret123"
    assert user.role == "user"


def test_register_rejects_short_password(session):
    with pytest.raises(ValueError):
        AuthService(session).register("bob", "123")


def test_register_rejects_duplicate_username(session):
    auth = AuthService(session)
    auth.register("carol", "secret123")
    with pytest.raises(ValueError):
        auth.register("carol", "another1")


def test_authenticate_success_and_failure(session):
    auth = AuthService(session)
    auth.register("dave", "secret123")
    assert auth.authenticate("dave", "secret123") is not None
    assert auth.authenticate("dave", "wrongpass") is None
    assert auth.authenticate("nobody", "secret123") is None


# --- Route-level ---------------------------------------------------------
def test_register_logs_in_and_redirects(client):
    resp = client.post(
        "/register",
        data={"username": "erin", "password": "secret123"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Dashboard" in resp.data  # landed on the dashboard


def test_login_logout_cycle(client):
    client.post("/register", data={"username": "frank", "password": "secret123"})
    # register logs us in and clears session on logout
    client.post("/logout")
    # now protected page redirects to login
    assert "/login" in client.get("/").headers["Location"]
    # log back in
    client.post("/login", data={"username": "frank", "password": "secret123"})
    assert client.get("/").status_code == 200


def test_bad_login_shows_error(client):
    client.post("/register", data={"username": "gina", "password": "secret123"})
    client.post("/logout")
    resp = client.post(
        "/login",
        data={"username": "gina", "password": "nope"},
        follow_redirects=True,
    )
    assert b"Invalid username or password" in resp.data
