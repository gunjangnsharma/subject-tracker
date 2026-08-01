"""Application factory.

Wires configuration, the database, template filters and blueprints together.
Keeping this in a factory lets tests build an isolated in-memory app instance.
"""

from __future__ import annotations

from flask import Flask, g

from tracker.config import DEFAULT_SECRET, Config, get_config, resolve_settings
from tracker.database import Database
from tracker.domain import format_hm


def create_app(config: type[Config] | Config | None = None) -> Flask:
    # No explicit config → resolve from SUBJECT_TRACKER_ENV (dev/prod/test).
    if config is None:
        config = get_config()

    app = Flask(__name__)
    app.config.from_object(config)
    # Fill in the settings the config leaves to the environment (DB URL, secret,
    # cookie-Secure flag). Done here, not at import time, so the values reflect
    # the environment this process actually starts with.
    app.config.update(resolve_settings(config))

    # Production must never run with the shipped dev secret.
    if app.config.get("ENV") == "prod" and app.config["SECRET_KEY"] == DEFAULT_SECRET:
        raise RuntimeError(
            "Refusing to start in production with the default SECRET_KEY. "
            "Set SUBJECT_TRACKER_SECRET to a long random value."
        )

    database = Database(app.config["DATABASE_URL"])
    database.create_all()
    app.database = database  # type: ignore[attr-defined]

    # One scoped session per request, exposed as g.session.
    @app.before_request
    def _open_session() -> None:
        g.session = database.Session()

    # After the session exists, resolve the logged-in user onto g.user.
    from tracker.auth import current_user, load_logged_in_user

    app.before_request(load_logged_in_user)

    # Make current_user available in every template.
    @app.context_processor
    def _inject_user() -> dict:
        return {"current_user": current_user()}

    # The chapter kinds, so the "add chapter" dropdown is generated from the
    # single source of truth (models.CHAPTER_KINDS) instead of hardcoded options.
    from tracker.models import CHAPTER_KINDS

    app.jinja_env.globals["chapter_kinds"] = CHAPTER_KINDS

    # Never cache rendered HTML pages (they change with the user's data), so the
    # browser can't show a stale view. Static assets keep their normal caching.
    @app.after_request
    def _no_store_html(response):
        if response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.teardown_request
    def _close_session(exc: BaseException | None) -> None:
        if exc is not None:
            database.Session.rollback()
        database.remove()

    # Jinja helper: render minutes as hours+minutes text (130 -> "2h 10m").
    @app.template_filter("hm")
    def _hm_filter(minutes: float) -> str:
        return format_hm(minutes)

    from tracker.routes.admin import bp as admin_bp
    from tracker.routes.auth import bp as auth_bp
    from tracker.routes.backup import bp as backup_bp
    from tracker.routes.dashboard import bp as dashboard_bp
    from tracker.routes.planning import bp as planning_bp
    from tracker.routes.subjects import bp as subjects_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(subjects_bp)
    app.register_blueprint(planning_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(backup_bp)

    return app
