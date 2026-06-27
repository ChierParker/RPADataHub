"""CompetitorWatch 数据库初始化脚本"""
import pymysql
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "RPADataHub"))
from config.settings import get_config

cfg = get_config()
print(f"Connecting to {cfg.database.host}:{cfg.database.port}/{cfg.database.database}...")
db = pymysql.connect(**cfg.database.as_dict())
cur = db.cursor()

# Read SQL file manually, skip comments, split by semicolon
sql_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "init_tables.sql")
with open(sql_file, 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()

# Filter out comment lines and BOM, then join
clean_lines = []
for line in lines:
    stripped = line.strip()
    if stripped and not stripped.startswith('--'):
        clean_lines.append(line)

content = ''.join(clean_lines)
statements = content.split(';')

for stmt in statements:
    stmt = stmt.strip()
    if stmt:
        try:
            cur.execute(stmt)
            first_line = stmt.split('\n')[0][:80]
            print(f"  OK: {first_line}")
        except pymysql.err.OperationalError as e:
            if e.args[0] == 1050:
                fl = stmt.split('\n')[0][:80]
                print(f"  EXISTS: {fl}")
            else:
                print(f"  ERROR: {e}")

db.commit()

# Verify
for table in ['competitor_config', 'ods_price_snapshot', 'dw_competitor_daily', 'competitor_report']:
    cur.execute(f"SHOW TABLES LIKE '{table}'")
    exists = bool(cur.fetchone())
    print(f"  {table}: {'✓' if exists else '✗'}")

cur.close()
db.close()
print("\nCompetitorWatch 数据库初始化完成!")