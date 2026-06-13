"""
配置中心
- 所有硬编码配置外置
- 支持环境变量覆盖（前缀 RPA_）
- 配置项覆盖：数据库/告警/路径/重试策略/校验规则开关/降频阈值
对应白皮书：
  2.3.2 可扩展性：配置化接入，新增平台只需配置规则
  3.3.1 采集框架设计：配置化驱动
"""

import os
from dataclasses import dataclass, field

# 自动加载项目根目录下的 .env 文件（若存在）
# 必须在 dataclass 字段默认值求值之前执行，否则 _env() 读不到环境变量
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.isfile(_env_file):
        _load_dotenv(_env_file, override=False)
except ImportError:
    pass  # python-dotenv 未安装时静默跳过


def _env(key, default):
    """读取环境变量，不存在则返回默认值"""
    return os.environ.get(f"RPA_{key}", default)


# ============================================================
# 数据库配置
# ============================================================

@dataclass
class DatabaseConfig:
    host: str = _env("DB_HOST", "localhost")
    port: int = int(_env("DB_PORT", "3306"))
    user: str = _env("DB_USER", "root")
    password: str = _env("DB_PASSWORD", "your-db-password")
    database: str = _env("DB_DATABASE", "data")
    charset: str = "utf8mb4"
    # 连接池参数
    pool_min_size: int = 2
    pool_max_size: int = 10
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
# 路径配置
# ============================================================

@dataclass
class PathConfig:
    # 监听文件夹
    watch_folder: str = _env("WATCH_FOLDER", r"D:\rpa_output")
    # 归档文件夹
    archive_folder: str = _env("ARCHIVE_FOLDER", r"D:\rpa_archive")
    # 日志目录
    log_dir: str = _env("LOG_DIR", r"D:\RPADataHub\rpa_logs")
    # 兜底数据目录（数据库不可用时写入本地JSON）
    fallback_dir: str = _env("FALLBACK_DIR", r"D:\rpa_fallback")


# ============================================================
# 告警配置
# ============================================================

@dataclass
class AlertConfig:
    # DeepSeek API Key
    deepseek_api_key: str = _env("DEEPSEEK_API_KEY", "your-deepseek-api-key")
    # Bark推送URL
    bark_url: str = _env("BARK_URL", "https://api.day.app/your-bark-key")
    # 钉钉/企业微信 Webhook（预留）
    dingtalk_webhook: str = _env("DINGTALK_WEBHOOK", "")
    wechat_webhook: str = _env("WECHAT_WEBHOOK", "")

    # P0级别告警：需要声音提醒
    p0_sound: bool = True
    # 告警抑制：同一类型告警N分钟内只发一次
    alert_suppress_minutes: int = 15


# ============================================================
# 重试与自愈配置
# ============================================================

@dataclass
class RetryConfig:
    # 临时异常最大重试次数（网络超时、文件锁定等）
    max_retries: int = 3
    # 重试间隔基数（秒），指数退避: base * (2 ** attempt)
    retry_base_delay: float = 1.0
    # 最大重试间隔（秒）
    retry_max_delay: float = 30.0
    # 可重试的异常类型关键字
    retryable_keywords: tuple = (
        "timeout", "connection", "locked", "permission",
        "OSError", "BlockingIOError", "temporary",
    )


# ============================================================
# 数据校验配置
# ============================================================

@dataclass
class ValidationConfig:
    # 数据量骤降告警阈值（相比7日均值降幅百分比）
    volume_drop_threshold_pct: float = 50.0

    # 单文件脏数据告警阈值（条数）
    dirty_data_warn_threshold: int = 5
    dirty_data_block_threshold: int = 20

    # 注意：字段类型/非空/格式校验已改为 MySQL Schema 兜底
    # 代码层不再做字段级预校验，每接入新表无需修改此处配置


# ============================================================
# 低频降频配置
# ============================================================

@dataclass
class LowFrequencyConfig:
    # 连续N天无数据触发降频
    trigger_days: int = 7
    # 降频后检查周期（每周二 = 1，对应 cron: 0 9 * * 2）
    check_day_of_week: int = 1  # Monday=0, Tuesday=1


# ============================================================
# Redis 消息队列配置
# ============================================================

@dataclass
class RedisConfig:
    redis_url: str = _env("REDIS_URL", "redis://:your-redis-password@localhost:6379")


# ============================================================
# 双轨采集验证配置
# ============================================================

@dataclass
class DualTrackConfig:
    # 是否启用API双向验证
    enabled: bool = _env("DUAL_TRACK_ENABLED", "false").lower() == "true"
    # API数据源端点（预留）
    api_endpoint: str = _env("API_ENDPOINT", "")
    # 数据量差异容忍度（百分比）
    diff_tolerance_pct: float = 5.0


# ============================================================
# 聚合配置
# ============================================================

@dataclass
class AppConfig:
    """应用配置聚合"""
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    alert: AlertConfig = field(default_factory=AlertConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    low_freq: LowFrequencyConfig = field(default_factory=LowFrequencyConfig)
    dual_track: DualTrackConfig = field(default_factory=DualTrackConfig)


# ============================================================
# 全局单例
# ============================================================

_config_instance = None


def get_config() -> AppConfig:
    """获取全局配置单例（首次调用时校验关键配置）"""
    global _config_instance
    if _config_instance is None:
        _config_instance = AppConfig()
        _validate_critical_config(_config_instance)
    return _config_instance


# 标记为占位符的关键配置默认值
_PLACEHOLDER_VALUES = {
    "your-db-password",
    "your-deepseek-api-key",
    "your-bark-key",
    "your-redis-password",
}


def _is_placeholder(value: str) -> bool:
    """检查配置值是否为占位符"""
    return any(p in str(value) for p in _PLACEHOLDER_VALUES)


def _validate_critical_config(cfg: AppConfig):
    """校验关键配置：占位符仅告警，不阻断启动"""
    import sys as _sys
    warnings = []

    if _is_placeholder(cfg.database.password):
        warnings.append("RPA_DB_PASSWORD 仍为占位符，请设置真实数据库密码")
    if _is_placeholder(cfg.alert.deepseek_api_key):
        warnings.append("RPA_DEEPSEEK_API_KEY 仍为占位符，AI 功能将不可用")
    if _is_placeholder(cfg.alert.bark_url):
        warnings.append("RPA_BARK_URL 仍为占位符，Bark 告警推送将不可用")
    if _is_placeholder(cfg.redis.redis_url):
        warnings.append("RPA_REDIS_URL 仍为占位符，将自动降级为 DB 轮询模式")

    if warnings:
        print("[Config] 警告：以下配置项使用了占位符值：", file=_sys.stderr)
        for w in warnings:
            print(f"  ⚠ {w}", file=_sys.stderr)
        print("[Config] 如需正常运行，请在 .env 文件中设置对应的环境变量", file=_sys.stderr)


def reload_config():
    """重新加载配置（运行时不重启更新）"""
    global _config_instance
    _config_instance = AppConfig()
    return _config_instance
