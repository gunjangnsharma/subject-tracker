"""Tests for dev / prod / test environment configuration."""

import pytest

from tracker import create_app
from tracker.config import (
    DEFAULT_SECRET,
    DevConfig,
    ProdConfig,
    TestConfig,
    get_config,
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


def test_default_create_app_is_dev(monkeypatch):
    # No SUBJECT_TRACKER_ENV → dev.
    monkeypatch.delenv("SUBJECT_TRACKER_ENV", raising=False)
    monkeypatch.setenv("SUBJECT_TRACKER_DB", "sqlite:///:memory:")
    app = create_app()
    assert app.config["ENV"] == "dev"
    app.database.remove()  # type: ignore[attr-defined]
