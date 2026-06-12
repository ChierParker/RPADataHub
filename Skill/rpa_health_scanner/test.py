"""
rpa-health-scanner 测试脚本
用法: cd RPADataHub && python Skill/rpa-health-scanner/test.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from main import scan
from config.settings import get_config
import pymysql, pandas as pd


def db_query(sql, params=None):
    """模拟 admin_server 的 query 函数"""
    cfg = get_config()
    conn = pymysql.connect(**cfg.database.as_dict())
    try:
        df = pd.read_sql(sql, conn, params=params)
        return df
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 50)
    print("  rpa-health-scanner 测试")
    print("=" * 50)
    result = scan(db_query)
    print(f"\n综合评分: {result['overall_score']} / 综合评级: {result['overall_grade']}")
    print(f"\n模块详情:")
    for m in result["modules"]:
        emoji = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}
        print(f"  {emoji.get(m['grade'], '⚪')} {m['name']}: {m['value']}")
    if result.get("suggestions"):
        print(f"\n建议:")
        for s in result["suggestions"]:
            print(f"  ⚠ {s}")
    print("\n测试完成!")
