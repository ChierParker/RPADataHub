"""
新浪财经-要闻采集器（BaseCollector 实现）
目标: https://finance.sina.com.cn/
"""

import time
from datetime import datetime
from collectors.base import BaseCollector
from schemas.task_schema import TaskConfig
from schemas.result_schema import TaskSummary

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


class SinaFinanceCollector(BaseCollector):
    """新浪财经要闻采集器"""

    collector_name = "sina_finance"
    supported_platforms = ["Sina"]
    default_ods_table = "ods_sina_news_raw"

    def run(self, config: TaskConfig) -> TaskSummary:
        articles, output_file = self._crawl(
            headless=True,
            max_articles=50,
            output_dir=str(self.get_output_dir())
        )

        # 记录结果
        row_count = len(articles)
        if row_count > 0:
            self.add_record(
                shop_name="新浪财经",
                platform="Sina",
                result="SUCCESS",
                row_count=row_count,
                duration=int(time.time() - self._start_time)
            )
        else:
            self.add_record(
                shop_name="新浪财经",
                platform="Sina",
                result="NO_DATA",
                error="未采集到数据"
            )

        summary = self.build_summary(total_rows=row_count)
        summary.output_files = [output_file] if output_file else []
        return summary

    # ============================================================
    # 核心采集逻辑
    # ============================================================

    def _crawl(self, headless=True, max_articles=50, output_dir=""):
        if sync_playwright is None:
            raise ImportError("请安装: pip install playwright && playwright install chromium")

        articles = []
        output_file = ""

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = context.new_page()

            try:
                page.goto("https://finance.sina.com.cn/", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)

                # 多选择器降级
                selectors = [
                    ".m-p1-news-list .m-p1-news-list-item",
                    ".m-p1-news-list li",
                    ".m-hdline-news .m-hdline-news-item",
                    ".news-ctn .news-item",
                ]
                news_items = []
                for sel in selectors:
                    news_items = page.query_selector_all(sel)
                    if len(news_items) > 5:
                        break

                if news_items:
                    for item in news_items[:max_articles]:
                        try:
                            link_el = item.query_selector("a")
                            title = link_el.inner_text().strip() if link_el else ""
                            url = link_el.get_attribute("href") if link_el else ""
                            time_el = item.query_selector(".time, .date, [class*='time']")
                            pub_time = time_el.inner_text().strip() if time_el else ""
                            summary_el = item.query_selector(".summary, .desc, p")
                            summary = summary_el.inner_text().strip() if summary_el else ""
                            if title and url:
                                articles.append({
                                    "title": title, "url": url,
                                    "source": "新浪财经",
                                    "pub_time": pub_time,
                                    "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "category": "要闻", "summary": summary
                                })
                        except Exception:
                            continue
                else:
                    # 备用：提取所有财经链接
                    links = page.query_selector_all("a[href*='finance.sina.com.cn']")
                    for link in links:
                        text = link.inner_text().strip()
                        href = link.get_attribute("href")
                        if text and len(text) > 8 and href:
                            articles.append({
                                "title": text, "url": href,
                                "source": "新浪财经",
                                "pub_time": "",
                                "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "category": "要闻", "summary": ""
                            })

            except Exception as e:
                raise RuntimeError(f"新浪财经采集失败: {e}") from e
            finally:
                browser.close()

        # 去重
        seen = set()
        unique = []
        for a in articles:
            k = a["title"][:50]
            if k not in seen:
                seen.add(k)
                unique.append(a)
        articles = unique

        # 保存 Excel → RPA 监听目录 (D:/rpa_output/news/)
        import pandas as pd
        from pathlib import Path
        # 优先输出到 RPA 监听目录，file_watcher 会自动消费
        rpa_output = Path("D:/rpa_output/news")
        try:
            rpa_output.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            rpa_output = Path(output_dir) if output_dir else Path(__file__).resolve().parent.parent / "output"
            rpa_output.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = str(rpa_output / f"sina_news_{ts}.xlsx")
        pd.DataFrame(articles).to_excel(output_file, index=False)

        return articles, output_file
