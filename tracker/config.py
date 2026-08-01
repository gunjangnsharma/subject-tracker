"""Application configuration objects (dev / prod / test).

Pick an environment with the ``SUBJECT_TRACKER_ENV`` env var
(``dev`` | ``prod`` | ``test``; default ``dev``) — see ``get_config``.

Settings that come from the process environment are **declared** as ``FROM_ENV``
on the config classes and **resolved** by ``resolve_settings`` when the app is
built — not at import time. Reading them at import time meant the first
``import tracker.config`` froze the values, so anything that set an env var
afterwards was silently ignored.

Three collaborators, one job each:

* ``EnvSettings`` — reads values out of an environment mapping.
* the ``Config`` classes — declare per-environment policy (what differs).
* ``resolve_settings`` — combines the two into the final settings mapping.
"""

from __future__ import annotations

import os
from typing import Callable, Mapping

# The stand-in secret shipped for local dev. Production refuses to start with it.
DEFAULT_SECRET = "dev-secret-change-me"

# Default on-disk SQLite filename, created in the working directory.
DEFAULT_DB_FILENAME = "subject_tracker.db"

#: Marker for "the environment supplies this setting". A config class that
#: states a real value keeps it, so precedence is:
#: **explicit class value > env var > built-in default**.
FROM_ENV = None


class EnvSettings:
    """Reads app settings out of an environment mapping.

    Sole responsibility: translating environment variables into setting values.
    The mapping is injected, so callers and tests can pass their own dict
    instead of mutating ``os.environ``.
    """

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = os.environ if environ is None else environ

    def env_name(self, default: str = "dev") -> str:
        """Which environment to run as (``dev`` | ``prod`` | ``test``)."""
        return self._environ.get("SUBJECT_TRACKER_ENV", default).lower()

    def database_url(self) -> str:
        return self._environ.get("SUBJECT_TRACKER_DB", self._default_database_url())

    def secret_key(self) -> str:
        return self._environ.get("SUBJECT_TRACKER_SECRET", DEFAULT_SECRET)

    def https(self) -> bool:
        """True when TLS terminates in front of us (marks cookies Secure)."""
        return self._flag("SUBJECT_TRACKER_HTTPS")

    def _flag(self, name: str, default: bool = False) -> bool:
        raw = self._environ.get(name, "1" if default else "")
        return raw.lower() in ("1", "true", "yes", "on")

    @staticmethod
    def _default_database_url() -> str:
        # Built on demand so it follows the process's actual working directory.
        return "sqlite:///" + os.path.join(os.getcwd(), DEFAULT_DB_FILENAME)


class Config:
    """Base config shared by every environment.

    ``FROM_ENV`` settings are filled in by ``resolve_settings``; a subclass may
    override any of them with a concrete value.
    """

    DATABASE_URL = FROM_ENV
    SECRET_KEY = FROM_ENV
    # Only send the cookie over HTTPS when you're actually behind TLS.
    SESSION_COOKIE_SECURE = FROM_ENV

    # Cap uploaded backup files (defensive; a personal JSON backup is tiny).
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MB

    ENV = "base"
    DEBUG = False
    TEMPLATES_AUTO_RELOAD = False

    # Session-cookie hardening (safe in every environment).
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"


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


_CONFIGS: dict[str, type[Config]] = {
    "dev": DevConfig,
    "prod": ProdConfig,
    "test": TestConfig,
}

#: Setting name -> how to read it from the environment. Adding an env-backed
#: setting means adding a reader on EnvSettings and one line here.
_ENV_BACKED: dict[str, Callable[[EnvSettings], object]] = {
    "DATABASE_URL": lambda env: env.database_url(),
    "SECRET_KEY": lambda env: env.secret_key(),
    "SESSION_COOKIE_SECURE": lambda env: env.https(),
}


def get_config(
    name: str | None = None, environ: Mapping[str, str] | None = None
) -> type[Config]:
    """Resolve a config class by name, or from SUBJECT_TRACKER_ENV (default dev)."""
    key = name.lower() if name else EnvSettings(environ).env_name()
    return _CONFIGS.get(key, DevConfig)


def resolve_settings(
    config: type[Config] | Config | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Resolve *config*'s environment-backed settings into concrete values.

    Returns every env-backed setting name mapped to its final value: a value the
    config states explicitly is kept as-is; one left as ``FROM_ENV`` is read
    from the environment. Precedence is **explicit class value > env var >
    built-in default**.

    Called by ``create_app``, and by standalone scripts that need the same
    database URL the app would use.
    """
    target = get_config(environ=environ) if config is None else config
    env = EnvSettings(environ)
    return {
        name: read(env) if getattr(target, name, FROM_ENV) is FROM_ENV else getattr(target, name)
        for name, read in _ENV_BACKED.items()
    }
