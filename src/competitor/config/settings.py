"""
CompetitorWatch configuration center
- All configuration loaded from environment variables, no hardcoded credentials
- Supports .env auto-loading (via python-dotenv)
- Config priority: defaults < .env file < system env vars

Usage:
    from config.settings import get_config
    cfg = get_config()
    print(cfg.database.host)
"""

import os
from urllib.parse import quote
from dataclasses import dataclass, field

# Auto-load .env from project root
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
    )
    if os.path.isfile(_env_file):
        _load_dotenv(_env_file, override=False)
        print(f"[Config] Loaded .env: {_env_file}")
except ImportError:
    pass  # Silently skip if python-dotenv not installed


def _env(key, default=""):
    """Read environment variable, return default if not set."""
    return os.environ.get(key, default)


# ============================================================
# Database config
# ============================================================

@dataclass
class DatabaseConfig:
    host: str = _env("DB_HOST", "localhost")
    port: int = int(_env("DB_PORT", "3306"))
    user: str = _env("DB_USER", "root")
    password: str = _env("DB_PASSWORD", "")
    database: str = _env("DB_NAME", "ecomiq")
    charset: str = "utf8mb4"
    connect_timeout: int = 10

    def as_dict(self):
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "database": self.database,
            "charset": self.charset,
            "connect_timeout": self.connect_timeout,
        }


# ============================================================
# Redis config
# ============================================================

@dataclass
class RedisConfig:
    host: str = _env("REDIS_HOST", "localhost")
    port: int = int(_env("REDIS_PORT", "6379"))
    db: int = int(_env("REDIS_DB", "0"))
    password: str = _env("REDIS_PASSWORD", "")
    url: str = ""

    def __post_init__(self):
        if not self.url:
            if self.password:
                # URL-encode password to handle special chars like @ # $ % !
                encoded_pw = quote(self.password, safe="")
                self.url = f"redis://:{encoded_pw}@{self.host}:{self.port}/{self.db}"
            else:
                self.url = f"redis://{self.host}:{self.port}/{self.db}"


# ============================================================
# DeepSeek AI config
# ============================================================

@dataclass
class AIConfig:
    api_key: str = _env("DEEPSEEK_API_KEY", "")
    api_url: str = _env("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
    model: str = _env("DEEPSEEK_MODEL", "deepseek-chat")
    max_tokens: int = 2048
    temperature: float = 0.7


# ============================================================
# Proxy config (international collection)
# ============================================================

@dataclass
class ProxyConfig:
    http_proxy: str = _env("HTTP_PROXY", "")
    https_proxy: str = _env("HTTPS_PROXY", "")


# ============================================================
# Flask app config
# ============================================================

@dataclass
class FlaskConfig:
    secret_key: str = _env("FLASK_SECRET_KEY", "competitor-watch-2026-dev-key-change-in-prod")
    host: str = _env("FLASK_HOST", "0.0.0.0")
    port: int = int(_env("FLASK_PORT", "5100"))
    debug: bool = _env("FLASK_DEBUG", "false").lower() == "true"


# ============================================================
# Aggregate config
# ============================================================

@dataclass
class AppConfig:
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    flask: FlaskConfig = field(default_factory=FlaskConfig)


# ============================================================
# Global singleton
# ============================================================

_config_instance = None


def get_config() -> AppConfig:
    """Get global config singleton."""
    global _config_instance
    if _config_instance is None:
        _config_instance = AppConfig()
        _validate_config(_config_instance)
    return _config_instance


def _validate_config(cfg: AppConfig):
    """Validate critical config items."""
    import sys
    warnings = []

    placeholders = [
        "your-db-password", "your-api-key", "your-redis-password",
    ]

    if not cfg.database.password or any(p in cfg.database.password.lower() for p in placeholders):
        warnings.append("DB_PASSWORD not set or still a placeholder")
    if not cfg.ai.api_key or any(p in cfg.ai.api_key.lower() for p in placeholders):
        warnings.append("DEEPSEEK_API_KEY not set or still a placeholder (AI disabled)")

    if warnings:
        print("[Config] WARNING: the following config items need attention:", file=sys.stderr)
        for w in warnings:
            print(f"   - {w}", file=sys.stderr)
        print("[Config] Please configure them in your .env file", file=sys.stderr)
