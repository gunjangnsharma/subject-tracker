"""Tests for dev / prod / test environment configuration."""

import pytest

from tracker import create_app
from tracker.config import (
    DEFAULT_SECRET,
    DevConfig,
    EnvSettings,
    ProdConfig,
    TestConfig,
    get_config,
    resolve_settings,
)


def test_get_config_resolves_names():
    assert get_config("dev") is DevConfig
    assert get_config("prod") is ProdConfig
    assert get_config("test") is TestConfig
    assert get_config("nonsense") is DevConfig      # safe fallback


def test_get_config_reads_env(monkeypatch):
    monkeypatch.setenv("SUBJECT_TRACKER_ENV", "prod")
    assert get_config() is ProdConfig
    monkeypatch.delenv("SUBJECT_TRACKER_ENV", raising=False)
    assert get_config() is DevConfig                # default


def test_dev_reloads_templates_prod_caches():
    assert DevConfig.TEMPLATES_AUTO_RELOAD is True
    assert ProdConfig.TEMPLATES_AUTO_RELOAD is False


def test_prod_debug_off():
    assert ProdConfig.DEBUG is False


def test_prod_refuses_default_secret():
    class DefaultSecretProd(ProdConfig):
        SECRET_KEY = DEFAULT_SECRET
        DATABASE_URL = "sqlite:///:memory:"

    with pytest.raises(RuntimeError):
        create_app(DefaultSecretProd)


def test_prod_with_real_secret_starts():
    class RealProd(ProdConfig):
        SECRET_KEY = "a-long-random-production-secret"
        DATABASE_URL = "sqlite:///:memory:"

    app = create_app(RealProd)
    assert app.config["ENV"] == "prod"
    assert app.config["DEBUG"] is False
    app.database.remove()  # type: ignore[attr-defined]


def test_session_cookie_hardening():
    app = create_app(TestConfig)
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    app.database.remove()  # type: ignore[attr-defined]


def test_default_create_app_is_dev(monkeypatch, tmp_path):
    # No SUBJECT_TRACKER_ENV → dev.
    monkeypatch.delenv("SUBJECT_TRACKER_ENV", raising=False)
    monkeypatch.setenv("SUBJECT_TRACKER_DB", "sqlite:///:memory:")
    monkeypatch.chdir(tmp_path)   # belt and braces: never write into the repo
    app = create_app()
    assert app.config["ENV"] == "dev"
    # The env var is honoured even though it was set after tracker.config was
    # imported — settings resolve at create_app time, not at import time.
    assert app.config["DATABASE_URL"] == "sqlite:///:memory:"
    app.database.remove()  # type: ignore[attr-defined]


def test_env_settings_reads_an_injected_mapping():
    """EnvSettings takes its environment as a collaborator (no os.environ needed)."""
    env = EnvSettings(
        {
            "SUBJECT_TRACKER_ENV": "PROD",                # case-insensitive
            "SUBJECT_TRACKER_DB": "sqlite:///injected.db",
            "SUBJECT_TRACKER_SECRET": "injected-secret",
            "SUBJECT_TRACKER_HTTPS": "yes",
        }
    )
    assert env.env_name() == "prod"
    assert env.database_url() == "sqlite:///injected.db"
    assert env.secret_key() == "injected-secret"
    assert env.https() is True


def test_env_settings_defaults_when_unset():
    env = EnvSettings({})
    assert env.env_name() == "dev"
    assert env.secret_key() == DEFAULT_SECRET
    assert env.https() is False                      # HTTPS is opt-in
    assert env.database_url().startswith("sqlite:///")
    assert env.database_url().endswith("subject_tracker.db")


@pytest.mark.parametrize("raw,expected", [
    ("1", True), ("true", True), ("TRUE", True), ("yes", True), ("on", True),
    ("0", False), ("false", False), ("", False), ("nonsense", False),
])
def test_https_flag_parsing(raw, expected):
    assert EnvSettings({"SUBJECT_TRACKER_HTTPS": raw}).https() is expected


def test_explicit_config_value_beats_the_environment():
    """Precedence: explicit class value > env var > built-in default."""
    environ = {
        "SUBJECT_TRACKER_DB": "sqlite:///from-env.db",
        "SUBJECT_TRACKER_SECRET": "from-env",
    }
    settings = resolve_settings(TestConfig, environ)
    # TestConfig states its own DATABASE_URL, so the env var must not win...
    assert settings["DATABASE_URL"] == "sqlite:///:memory:"
    # ...but SECRET_KEY is left FROM_ENV, so it comes from the environment.
    assert settings["SECRET_KEY"] == "from-env"


def test_resolve_settings_falls_back_to_env_config(monkeypatch):
    """With no config passed, resolve_settings uses SUBJECT_TRACKER_ENV's class."""
    settings = resolve_settings(environ={"SUBJECT_TRACKER_ENV": "test"})
    assert settings["DATABASE_URL"] == "sqlite:///:memory:"
