"""Application factory.

Wires configuration, the database, template filters and blueprints together.
Keeping this in a factory lets tests build an isolated in-memory app instance.
"""

from __future__ import annotations

from flask import Flask, g

from tracker.config import Config
from tracker.database import Database
from tracker.domain import minutes_to_hours


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

    @app.teardown_request
    def _close_session(exc: BaseException | None) -> None:
        if exc is not None:
            database.Session.rollback()
        database.remove()

    # Jinja helper: render minutes as hours (90 -> "1.5").
    @app.template_filter("hours")
    def _hours_filter(minutes: float) -> str:
        return f"{minutes_to_hours(minutes):g}"

    from tracker.routes.planning import bp as planning_bp
    from tracker.routes.subjects import bp as subjects_bp

    app.register_blueprint(subjects_bp)
    app.register_blueprint(planning_bp)

    return app
