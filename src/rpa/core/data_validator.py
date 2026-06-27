"""
数据校验引擎（精简版）
核心理念（白皮书 4.2 节模板化接入）:
  → 字段类型/非空/唯一约束 → 交给 MySQL Schema 兜底
  → 代码只做 MySQL 做不了的事

保留的校验:
  L0 文件可读性  — 文件是否能正常打开
  L1 存在性校验  — 文件是否为空 + 数据量是否骤降（对比7日均值）
  L2 维表白名单  — 店铺名称是否在 dim_shop_info 中（业务规则，FK 无法表达）

移除的校验:
  L3 字段级校验   — 改为 MySQL Schema 兜底（类型/非空/格式/唯一键）
  原因: 每接入新表都要改代码配置必填字段，违背模板化接入原则
"""

import pandas as pd
from enum import Enum
from config.settings import get_config


class CheckResult(Enum):
    PASS = "PASS"
    WARN = "WARN"
    BLOCK = "BLOCK"


class ValidationReport:
    """单条校验报告"""

    def __init__(self, layer: str, rule_name: str, result: CheckResult, detail: str = ""):
        self.layer = layer
        self.rule_name = rule_name
        self.result = result
        self.detail = detail

    def __repr__(self):
        return f"[{self.layer}|{self.result.value}] {self.rule_name}: {self.detail}"


class DataValidator:
    """
    数据校验引擎
    只做 DB 做不了的校验：空文件 / 数据量骤降 / 维表白名单
    """

    def __init__(self, db_manager, trace_id="-"):
        self._db = db_manager
        self._trace_id = trace_id
        self._config = get_config().validation

    def check_empty_file(self, df, file_name):
        """
        L0: 文件是否为空
        返回: (reports, should_abort)
        """
        if df is None or df.empty:
            return [
                ValidationReport("L0-可读性", "文件为空",
                                 CheckResult.BLOCK,
                                 f"文件 {file_name} 无数据行，可能采集异常")
            ], True
        return [
            ValidationReport("L0-可读性", "文件非空",
                             CheckResult.PASS,
                             f"读取到 {len(df)} 条记录")
        ], False

    def check_volume_drop(self, df, ods_table, conn):
        """
        L1: 数据量骤降检测（对比7日均值）
        返回: [reports]
        """
        reports = []

        if ods_table is None:
            return reports

        try:
            avg_df = self._db.get_7day_avg_rows(conn, ods_table)
            if avg_df is not None and not avg_df.empty and avg_df["avg_cnt"].iloc[0]:
                avg_cnt = float(avg_df["avg_cnt"].iloc[0])
                today_cnt = len(df)
                if avg_cnt > 0:
                    drop_pct = (1 - today_cnt / avg_cnt) * 100
                    threshold = self._config.volume_drop_threshold_pct
                    if drop_pct > threshold:
                        reports.append(ValidationReport(
                            "L1-存在性", "数据量骤降",
                            CheckResult.WARN,
                            f"今日 {today_cnt} 条 vs 7日均值 {avg_cnt:.0f} 条，降幅 {drop_pct:.1f}%（阈值{threshold}%）"
                        ))
                    else:
                        reports.append(ValidationReport(
                            "L1-存在性", "数据量正常",
                            CheckResult.PASS,
                            f"今日 {today_cnt} 条 vs 7日均值 {avg_cnt:.0f} 条"
                        ))
        except Exception:
            # 7日均值查询失败不阻断
            pass

        return reports

    def run_validation(self, df, file_name, ods_table, conn):
        """
        执行全部代码层校验（空文件 + 数据量骤降）

        返回: (reports, worst_result)
        """
        all_reports = []

        # L0: 空文件检查
        reports, should_abort = self.check_empty_file(df, file_name)
        all_reports.extend(reports)
        if should_abort:
            return all_reports, CheckResult.BLOCK

        # L1: 数据量骤降
        all_reports.extend(self.check_volume_drop(df, ods_table, conn))

        # 确定最严重结果
        worst = CheckResult.PASS
        for r in all_reports:
            if r.result == CheckResult.BLOCK:
                worst = CheckResult.BLOCK
            elif r.result == CheckResult.WARN and worst != CheckResult.BLOCK:
                worst = CheckResult.WARN

        return all_reports, worst


# ============================================================
# 店铺维表校验器
# ============================================================

class ShopWhitelistValidator:
    """
    店铺维表校验器
    对应白皮书 2.5 节：维表驱动的数据校验 —— 白名单守门人

    这是业务规则级别的校验，MySQL 外键约束无法替代：
    - 维表有 status 字段区分活跃/停用
    - 店铺标识列名因表而异（订单表=shop_name，协议表=account）
    - 需要灵活的白名单/黑名单管理
    """

    def __init__(self, valid_shop_names=None):
        self._valid_shops = set(valid_shop_names) if valid_shop_names else set()

    @classmethod
    def from_db(cls, conn):
        """从数据库维表加载白名单"""
        df = pd.read_sql(
            "SELECT shop_name FROM dim_shop_info WHERE status = 1",
            conn
        )
        return cls(df["shop_name"].tolist())

    def is_valid(self, shop_name):
        """检查店铺名称是否在白名单中"""
        return str(shop_name).strip() in self._valid_shops

    def detect_shop_column(self, df):
        """
        自动检测DataFrame中的店铺标识列
        优先级: shop_name → account → 第一列
        """
        for candidate in ["shop_name", "account"]:
            if candidate in df.columns:
                return candidate
        return df.columns[0] if len(df.columns) > 0 else None

    def filter_valid(self, df, shop_col=None):
        """
        分离合法数据和脏数据

        参数:
          df: DataFrame
          shop_col: 店铺列名（None则自动检测）

        返回: (valid_df, dirty_df)
        """
        if shop_col is None:
            shop_col = self.detect_shop_column(df)

        if shop_col is None or shop_col not in df.columns:
            return df.copy(), pd.DataFrame()

        mask = df[shop_col].astype(str).str.strip().isin(self._valid_shops)
        return df[mask].copy(), df[~mask].copy()

    @property
    def shop_count(self):
        return len(self._valid_shops)
