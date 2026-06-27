# SQL 数据质量校验规则

## 规则分类

| 类别 | 层级 | 说明 |
|------|------|------|
| EXISTENCE | L1 存在性 | 数据是否存在、店铺是否有数据 |
| CONSISTENCY | L2 一致性 | 跨表数据是否一致、ODS/DW 对账 |
| COMPLETENESS | L3 完整性 | 关键字段是否缺失、数据格式是否合法 |

## 存在性校验 (L1)

### 店铺日度数据存在性
```sql
-- 检查每个活跃店铺今天是否有采集数据
SELECT ds.shop_name, ds.platform,
       MAX(o.create_time) AS last_time,
       CASE WHEN COUNT(o.id)=0 THEN '今日无数据' ELSE '正常' END AS status
FROM dim_shop_info ds
LEFT JOIN {ods_table} o ON ds.shop_name=o.shop_name AND DATE(o.create_time)=CURDATE()
WHERE ds.status=1
GROUP BY ds.shop_name, ds.platform
HAVING COUNT(o.id)=0;
```

### 数据量骤降检测
```sql
-- 今日数据量对比7日均值，降幅超过50%触发告警
SELECT today.cnt AS today_cnt,
       AVG(history.cnt) AS avg_7day,
       ROUND((1 - today.cnt / AVG(history.cnt)) * 100, 1) AS drop_pct
FROM (SELECT COUNT(*) cnt FROM {ods_table} WHERE DATE(create_time)=CURDATE()) today,
     (SELECT DATE(create_time) dt, COUNT(*) cnt FROM {ods_table}
      WHERE create_time>=DATE_SUB(CURDATE(),INTERVAL 7 DAY) AND create_time<CURDATE()
      GROUP BY DATE(create_time)) history
HAVING drop_pct > 50;
```

## 一致性校验 (L2)

### ODS-DW 对账
```sql
-- 检查 ODS 层有数据但 DW 层未聚合的记录
SELECT o.shop_name, o.order_date, COUNT(*) AS missing_cnt
FROM {ods_table} o
WHERE o.etl_status=0
  AND o.create_time < DATE_SUB(NOW(), INTERVAL 2 HOUR)
GROUP BY o.shop_name, o.order_date;
```

### 跨表数据一致性
```sql
-- 订单表有数据但费用表无对应记录
SELECT o.shop_name, DATE(o.order_date) dt, COUNT(DISTINCT o.po_number) orders,
       COUNT(DISTINCT f.invoice_id) fees
FROM ods_order_raw o
LEFT JOIN ods_fee_raw f ON o.shop_name=f.shop_name AND DATE(o.order_date)=DATE(f.fee_date)
WHERE DATE(o.order_date) >= DATE_SUB(CURDATE(),INTERVAL 7 DAY)
GROUP BY o.shop_name, DATE(o.order_date)
HAVING orders>0 AND fees=0;
```

## 完整性校验 (L3)

### 关键字段非空检测
```sql
-- 检查必填字段是否有 NULL 或空值
SELECT 'shop_name' AS field, COUNT(*) AS null_cnt FROM {ods_table} WHERE shop_name IS NULL OR shop_name=''
UNION ALL
SELECT 'po_number', COUNT(*) FROM {ods_table} WHERE po_number IS NULL OR po_number=''
UNION ALL
SELECT 'asin', COUNT(*) FROM {ods_table} WHERE asin IS NULL OR asin=''
UNION ALL
SELECT 'order_date', COUNT(*) FROM {ods_table} WHERE order_date IS NULL;
```

### ASIN 格式校验
```sql
-- ASIN 必须是 B 开头 + 10 位字母数字
SELECT COUNT(*) AS invalid_cnt
FROM {ods_table}
WHERE asin NOT REGEXP '^B[A-Z0-9]{9}$';
```

### 金额合理性校验
```sql
-- 金额不应为负数或超过合理范围
SELECT COUNT(*) AS abnormal_cnt
FROM {ods_table}
WHERE amount < 0 OR amount > 100000;
```

### 数据重复检测
```sql
-- 检查唯一键是否有重复
SELECT shop_name, po_number, asin, COUNT(*) AS dup_cnt
FROM {ods_table}
GROUP BY shop_name, po_number, asin
HAVING COUNT(*) > 1;
```

## 时效性校验

### 数据采集延迟检测
```sql
-- 店铺最近一次采集时间距离当前超过24小时
SELECT shop_name, MAX(crawl_time) AS last_crawl,
       TIMESTAMPDIFF(HOUR, MAX(crawl_time), NOW()) AS hours_ago
FROM ods_agreement_raw
GROUP BY shop_name
HAVING hours_ago > 24;
```

### 店铺采集频次检测
```sql
-- 近7天该店铺采集了几天（少于5天标记异常）
SELECT shop_name, COUNT(DISTINCT DATE(create_time)) AS active_days
FROM task_record
WHERE collect_result='SUCCESS' AND create_time>=DATE_SUB(CURDATE(),INTERVAL 7 DAY)
GROUP BY shop_name
HAVING active_days < 5;
```

## 使用说明

1. 将规则 SQL 中的 `{ods_table}` 替换为实际表名
2. 在 Admin → SQL巡检 → 新增监控 SQL 中添加
3. 根据业务需求调整阈值参数
4. 建议 P0 规则配置每小时执行，P1/P2 每日执行
