"""Application configuration objects (dev / prod / test).

Pick an environment with the ``SUBJECT_TRACKER_ENV`` env var
(``dev`` | ``prod`` | ``test``; default ``dev``) — see ``get_config``.
Individual values are still overridable via their own env vars.
"""

from __future__ import annotations

import os

# The stand-in secret shipped for local dev. Production refuses to start with it.
DEFAULT_SECRET = "dev-secret-change-me"


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "1" if default else "").lower() in ("1", "true", "yes", "on")


class Config:
    """Base config shared by every environment. Override via env vars."""

    # Default on-disk SQLite database, sitting next to the package.
    DATABASE_URL = os.environ.get(
        "SUBJECT_TRACKER_DB",
        "sqlite:///" + os.path.join(os.getcwd(), "subject_tracker.db"),
    )
    SECRET_KEY = os.environ.get("SUBJECT_TRACKER_SECRET", DEFAULT_SECRET)

    # Cap uploaded backup files (defensive; a personal JSON backup is tiny).
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MB

    ENV = "base"
    DEBUG = False
    TEMPLATES_AUTO_RELOAD = False

    # Session-cookie hardening (safe in every environment).
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Only send the cookie over HTTPS when you're actually behind TLS.
    SESSION_COOKIE_SECURE = _env_bool("SUBJECT_TRACKER_HTTPS")


class DevConfig(Config):
    """Local development: reload templates on change, friendlier errors."""

    ENV = "dev"
    TEMPLATES_AUTO_RELOAD = True


class ProdConfig(Config):
    """Production: no debugger, cached templates. Served by a real WSGI server.

    Refuses to start with the default SECRET_KEY (enforced in create_app).
    """

    ENV = "prod"
    DEBUG = False
    TEMPLATES_AUTO_RELOAD = False


class TestConfig(Config):
    """Tests: fast, isolated, in-memory database."""

    ENV = "test"
    DATABASE_URL = "sqlite:///:memory:"
    TESTING = True


_CONFIGS = {"dev": DevConfig, "prod": ProdConfig, "test": TestConfig}


def get_config(name: str | None = None) -> type[Config]:
    """Resolve a config class by name, or from SUBJECT_TRACKER_ENV (default dev)."""
    key = (name or os.environ.get("SUBJECT_TRACKER_ENV", "dev")).lower()
    return _CONFIGS.get(key, DevConfig)
