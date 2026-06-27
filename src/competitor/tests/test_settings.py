"""Tests for config/settings.py module."""

import os
import pytest
from config.settings import get_config, AppConfig, DatabaseConfig, RedisConfig, AIConfig


class TestSettings:

    def test_get_config_returns_singleton(self):
        """Config should be a singleton."""
        cfg1 = get_config()
        cfg2 = get_config()
        assert cfg1 is cfg2

    def test_get_config_type(self):
        """get_config should return AppConfig."""
        cfg = get_config()
        assert isinstance(cfg, AppConfig)

    def test_database_defaults(self):
        """DatabaseConfig should have sensible defaults."""
        cfg = get_config()
        assert cfg.database.host == "localhost"
        assert cfg.database.port == 3306
        assert cfg.database.charset == "utf8mb4"

    def test_redis_url_built(self):
        """RedisConfig should build URL from components."""
        cfg = get_config()
        assert cfg.redis.url, "Redis URL should be built"
        assert cfg.redis.url.startswith("redis://")

    def test_flask_defaults(self):
        """FlaskConfig should have sensible defaults."""
        cfg = get_config()
        assert cfg.flask.port == 5100
        assert cfg.flask.host == "0.0.0.0"
        assert not cfg.flask.debug

    def test_app_config_structure(self):
        """AppConfig should contain all sub-config sections."""
        cfg = get_config()
        assert isinstance(cfg.database, DatabaseConfig)
        assert isinstance(cfg.redis, RedisConfig)
        assert isinstance(cfg.ai, AIConfig)
        assert hasattr(cfg, "proxy")
        assert hasattr(cfg, "flask")

    def test_ai_config_has_sensible_defaults(self):
        """AI config should have default model and URL."""
        cfg = get_config()
        assert cfg.ai.model == "deepseek-chat"
        assert "deepseek.com" in cfg.ai.api_url
        assert cfg.ai.temperature == 0.7

    def test_database_as_dict(self):
        """DatabaseConfig.as_dict should return connection kwargs."""
        cfg = get_config()
        d = cfg.database.as_dict()
        assert d["host"] == "localhost"
        assert d["port"] == 3306
        assert d["charset"] == "utf8mb4"
        assert "password" in d
