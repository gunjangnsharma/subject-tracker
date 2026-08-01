"""Application factory.

Wires configuration, the database, template filters and blueprints together.
Keeping this in a factory lets tests build an isolated in-memory app instance.
"""

from __future__ import annotations

from flask import Flask, g

from tracker.config import Config
from tracker.database import Database
from tracker.domain import format_hm


def create_app(config: type[Config] | Config = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config)

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
