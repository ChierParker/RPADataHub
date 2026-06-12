"""
分级告警管理器
对应白皮书第7章：告警与运维自动化

告警等级:
  P0-紧急: 数据量骤降>80%、ETL阻断、数据库连接失败 → 实时推送 + 声音
  P1-重要: 脏数据>10条、校验WARN、DW聚合失败 → 实时推送
  P2-一般: 单条脏数据、低频店铺标记 → 仅看板/日志

告警抑制: 同一类型告警N分钟内只发一次
低频降频机制: 连续7天无数据 → 标记低频 → 每周二恢复检查

对应白皮书：
  7.1 告警发现机制: SQL监控主动发现
  7.2 告警通知: 精准触达责任人
  7.3 低频账号降频机制
"""

import time
import threading
from datetime import datetime, timedelta
from enum import Enum
from config.settings import get_config


class AlertLevel(Enum):
    P0 = "P0-紧急"
    P1 = "P1-重要"
    P2 = "P2-一般"


class AlertManager:
    """
    分级告警管理器

    使用方式:
        alert_mgr = AlertManager(logger)
        alert_mgr.send(AlertLevel.P1, "脏数据告警", "文件xxx有15条脏数据", trace_id)
    """

    def __init__(self, logger):
        self._logger = logger
        self._config = get_config().alert
        self._suppress_map = {}  # key: (alert_type, title) → last_send_time
        self._lock = threading.Lock()

    # ============================================================
    # 告警发送
    # ============================================================

    def send(self, level, title, content, trace_id="-", bypass_suppress=False):
        """
        发送告警
        level: AlertLevel 枚举
        title: 告警标题
        content: 告警内容
        trace_id: 全链路追踪ID
        bypass_suppress: 绕过抑制（P0默认绕过）
        """
        # P0 级别绕过抑制
        if level == AlertLevel.P0:
            bypass_suppress = True

        # 告警抑制检查
        if not bypass_suppress and self._is_suppressed(level, title):
            self._logger.info(
                f"[告警抑制] {level.value} | {title} | 同类型告警在{self._config.alert_suppress_minutes}分钟内已发送",
                trace_id
            )
            return False

        # 记录发送时间
        with self._lock:
            self._suppress_map[(level.value, title)] = time.time()

        # P0/P1 实时推送
        if level in (AlertLevel.P0, AlertLevel.P1):
            self._push_bark(title, content, level, trace_id)

        # P2 仅记日志
        if level == AlertLevel.P2:
            self._logger.info(
                f"[告警|{level.value}] {title} | {content}",
                trace_id
            )
        else:
            self._logger.warning(
                f"[告警|{level.value}] {title} | {content}",
                trace_id
            )

        return True

    def send_p0(self, title, content, trace_id="-"):
        """P0紧急告警快捷方法"""
        return self.send(AlertLevel.P0, title, content, trace_id)

    def send_p1(self, title, content, trace_id="-"):
        """P1重要告警快捷方法"""
        return self.send(AlertLevel.P1, title, content, trace_id)

    def send_p2(self, title, content, trace_id="-"):
        """P2一般告警快捷方法"""
        return self.send(AlertLevel.P2, title, content, trace_id)

    # ============================================================
    # Bark 推送
    # ============================================================

    def _push_bark(self, title, content, level, trace_id):
        """通过Bark推送告警"""
        bark_url = self._config.bark_url
        if not bark_url:
            self._logger.info(
                f"[Bark未配置] {level.value}: {title} - {content}",
                trace_id
            )
            return

        try:
            import requests
            # P0 级别加声音
            sound_suffix = "?sound=alarm" if (level == AlertLevel.P0 and self._config.p0_sound) else ""
            level_prefix = f"[{level.value}] "
            url = f"{bark_url}/{level_prefix}{title}/{content}{sound_suffix}"
            requests.get(url, timeout=5)
            self._logger.info(
                f"[Bark推送成功|{level.value}] {title}",
                trace_id
            )
        except Exception as e:
            self._logger.error(
                f"[Bark发送失败|{level.value}] {e}",
                trace_id
            )

    # ============================================================
    # 告警抑制
    # ============================================================

    def _is_suppressed(self, level, title):
        """检查告警是否应被抑制"""
        suppress_key = (level.value, title)
        last_time = self._suppress_map.get(suppress_key)
        if last_time is None:
            return False

        elapsed = time.time() - last_time
        return elapsed < (self._config.alert_suppress_minutes * 60)

    def clear_suppression(self):
        """清除告警抑制记录"""
        with self._lock:
            self._suppress_map.clear()


class LowFrequencyManager:
    """
    低频账号降频管理器
    对应白皮书 7.3 节：低频账号降频机制

    触发条件: 店铺连续7天无数据
    执行动作: 自动标记为低频，监控频率降至每周二一次
    恢复条件: 数据恢复后自动移出低频名单
    """

    def __init__(self, db_manager, alert_manager, trace_id="-"):
        self._db = db_manager
        self._alert = alert_manager
        self._trace_id = trace_id
        self._config = get_config().low_freq

    def check_and_update(self, conn, shop_name, platform, has_data):
        """
        更新店铺活跃状态，必要时触发降频/恢复

        参数:
          conn: 数据库连接
          shop_name: 店铺名
          platform: 平台名
          has_data: 今日是否有数据
        """
        self._db.update_shop_activity(conn, shop_name, platform, has_data)

        if not has_data:
            # 检查是否达到降频阈值
            low_freq_shops = self._db.get_low_frequency_shops(conn)
            for _, row in low_freq_shops.iterrows():
                if row["shop_name"] == shop_name:
                    days = row["consecutive_empty_days"]
                    if days >= self._config.trigger_days:
                        self._db.mark_low_frequency(conn, shop_name)
                        self._alert.send_p2(
                            "低频店铺标记",
                            f"店铺 {shop_name}({platform}) 连续{days}天无数据，已标记为低频，每周二恢复检查"
                        )

    def should_skip_monitoring(self, conn, shop_name):
        """检查店铺是否应跳过日常监控（已被降频）"""
        sql = """
            SELECT is_low_freq FROM low_frequency_shops
            WHERE shop_name = %s AND is_low_freq = 1
        """
        with conn.cursor() as cursor:
            cursor.execute(sql, (shop_name,))
            result = cursor.fetchone()
        if result:
            # 检查是否到了周二检查日
            today = datetime.now()
            if today.weekday() != self._config.check_day_of_week:
                return True  # 跳过，未到检查日
        return False

    def restore_if_active(self, conn, shop_name):
        """如果店铺恢复数据，移出低频名单"""
        sql = """
            UPDATE low_frequency_shops
            SET is_low_freq = 0, consecutive_empty_days = 0, next_check_date = NULL
            WHERE shop_name = %s AND is_low_freq = 1
        """
        with conn.cursor() as cursor:
            cursor.execute(sql, (shop_name,))
        conn.commit()
