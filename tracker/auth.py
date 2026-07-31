"""Session-based authentication helpers.

Kept dependency-free (just Flask's signed session cookie + Werkzeug hashing in
AuthService). ``load_logged_in_user`` runs before each request to populate
``g.user``; the decorators gate views on being logged in / being an admin.
"""

from __future__ import annotations

import functools

from flask import g, redirect, session, url_for
from werkzeug.exceptions import Forbidden

from tracker.models import User
from tracker.services.auth_service import AuthService

SESSION_KEY = "user_id"


def login_user(user: User) -> None:
    session.clear()
    session[SESSION_KEY] = user.id


def logout_user() -> None:
    session.clear()


def current_user() -> User | None:
    return g.get("user")


def load_logged_in_user() -> None:
    """before_request hook: attach the logged-in User (or None) to ``g.user``."""
    user_id = session.get(SESSION_KEY)
    g.user = AuthService(g.session).get(user_id) if user_id is not None else None


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None:
            return redirect(url_for("auth.login"))
        if not user.is_admin:
            raise Forbidden("Admins only.")
        return view(*args, **kwargs)

    return wrapped
