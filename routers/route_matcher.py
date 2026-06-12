"""
配置化路由匹配器（文件夹优先 + DW加工SQL配置化）
对应白皮书 2.3.2 节：平台接入模板化
          4.2 节：数据开发工程师通过配置SQL驱动DW加工

路由策略（两级降级）:
  Tier 1: 文件夹匹配 (etl_path_route) — 精确度最高，推荐方式
          文件所在路径包含 pattern 即命中
          一个文件夹 = 一张ODS表 + 一条DW加工SQL
  Tier 2: 文件名匹配 (etl_route_config) — 兜底策略

设计原则:
  文件夹即表，SQL即加工 — ODS→DW 由数据开发工程师写SQL配置，代码零改动
"""

from collections import namedtuple

# 路由匹配结果
RouteResult = namedtuple("RouteResult", ["ods_table", "dw_table", "dw_sql", "skip_whitelist", "method"])


class RouteMatcher:

    def match(self, conn, file_name, relative_path):
        """
        两级路由匹配（文件夹优先）

        返回: RouteResult(ods_table, dw_table, dw_sql, method)
              dw_sql 为 None 表示不执行DW加工
        """
        # Tier 1: 文件夹匹配
        result = self._match_by_folder(conn, relative_path)
        if result:
            return result._replace(method="folder")

        # Tier 2: 文件名匹配
        result = self._match_by_filename(conn, file_name)
        if result:
            return result._replace(method="filename")

        return RouteResult(None, None, None, False, None)

    # ============================================================
    # Tier 1: 文件夹路由匹配
    # ============================================================

    def _match_by_folder(self, conn, relative_path):
        import pandas as pd

        try:
            routes = pd.read_sql(
                "SELECT path_pattern, target_ods_table, target_dw_table, dw_transform_sql, COALESCE(skip_whitelist,0) as skip_whitelist "
                "FROM etl_path_route WHERE is_active = 1",
                conn
            )
        except Exception:
            return None

        if routes.empty:
            return None

        rel_path = relative_path.replace("\\", "/").strip("/")

        for _, row in routes.iterrows():
            pattern = str(row["path_pattern"]).replace("\\", "/").strip("/")
            if pattern and pattern in rel_path:
                dw_sql = row.get("dw_transform_sql")
                # pandas NaN → None
                if pd.isna(dw_sql) if isinstance(dw_sql, float) else False:
                    dw_sql = None
                return RouteResult(
                    row["target_ods_table"],
                    row["target_dw_table"],
                    dw_sql,
                    bool(row.get("skip_whitelist", 0)),
                    None
                )

        return None

    # ============================================================
    # Tier 2: 文件名路由匹配（兜底）
    # ============================================================

    def _match_by_filename(self, conn, file_name):
        import pandas as pd

        try:
            routes = pd.read_sql(
                "SELECT file_pattern, target_ods_table, target_dw_table, dw_transform_sql, COALESCE(skip_whitelist,0) as skip_whitelist "
                "FROM etl_route_config WHERE is_active = 1",
                conn
            )
        except Exception:
            return None

        if routes.empty:
            return None

        name_lower = file_name.lower()
        for _, row in routes.iterrows():
            pattern = str(row.get("file_pattern", "")).lower()
            if pattern and pattern in name_lower:
                dw_sql = row.get("dw_transform_sql")
                if pd.isna(dw_sql) if isinstance(dw_sql, float) else False:
                    dw_sql = None
                return RouteResult(
                    row["target_ods_table"],
                    row["target_dw_table"],
                    dw_sql,
                    bool(row.get("skip_whitelist", 0)),
                    None
                )

        return None

    # ============================================================
    # 工具方法
    # ============================================================

    def get_all_routes(self, conn):
        import pandas as pd
        path_routes = pd.read_sql(
            "SELECT path_pattern, target_ods_table, target_dw_table, "
            "CASE WHEN dw_transform_sql IS NOT NULL THEN 'Y' ELSE 'N' END AS has_dw_sql, is_active "
            "FROM etl_path_route", conn
        )
        file_routes = pd.read_sql(
            "SELECT file_pattern, target_ods_table, target_dw_table, "
            "CASE WHEN dw_transform_sql IS NOT NULL THEN 'Y' ELSE 'N' END AS has_dw_sql, is_active "
            "FROM etl_route_config", conn
        )
        return {
            "folder_routes": path_routes.to_dict("records"),
            "file_routes": file_routes.to_dict("records"),
        }
