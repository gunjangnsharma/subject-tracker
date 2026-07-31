"""Authentication routes: register, login, logout."""

from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from tracker.auth import current_user, login_user, logout_user
from tracker.services.auth_service import AuthService

bp = Blueprint("auth", __name__)


def _service() -> AuthService:
    return AuthService(g.session)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user() is not None:
        return redirect(url_for("dashboard.home"))
    if request.method == "POST":
        try:
            user = _service().register(
                request.form.get("username", ""),
                request.form.get("password", ""),
            )
            login_user(user)
            flash("Welcome! Your account is ready.", "info")
            return redirect(url_for("dashboard.home"))
        except ValueError as exc:
            flash(str(exc), "error")
    return render_template("auth/register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user() is not None:
        return redirect(url_for("dashboard.home"))
    if request.method == "POST":
        user = _service().authenticate(
            request.form.get("username", ""),
            request.form.get("password", ""),
        )
        if user is None:
            flash("Invalid username or password.", "error")
        else:
            login_user(user)
            return redirect(url_for("dashboard.home"))
    return render_template("auth/login.html")


@bp.post("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
