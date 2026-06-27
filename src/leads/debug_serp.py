"""
Google SERP 结构诊断脚本
======================
启动浏览器 → 执行搜索 → 保存完整HTML和截图到 debug/ 目录
用于分析真实的 Google 搜索结果 DOM 结构，适配提取规则。
"""

import time
from pathlib import Path
from playwright.sync_api import sync_playwright

from config import GOOGLE_HOME, GOOGLE_SEARCH_SELECTOR, DEFAULT_USER_AGENT, BROWSER_DIR

DEBUG_DIR = Path(__file__).parent / "debug"
DEBUG_DIR.mkdir(exist_ok=True)

# 测试关键词
KEYWORDS = [
    'auto parts WhatsApp "+44"',
    'auto parts email contact "@de"',
]

def main():
    pw = sync_playwright().start()

    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--start-maximized",
    ]

    chrome_exe = BROWSER_DIR / "chrome-win" / "chrome.exe"
    launch_opts = {
        "headless": False,
        "args": args,
    }
    if chrome_exe.exists():
        launch_opts["executable_path"] = str(chrome_exe)

    # 使用独立 profile
    profile_dir = str(DEBUG_DIR / "browser_profile")
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    context = pw.chromium.launch_persistent_context(profile_dir, **launch_opts)
    context.set_extra_http_headers({"User-Agent": DEFAULT_USER_AGENT})
    page = context.new_page()
    page.set_viewport_size({"width": 1920, "height": 1080})

    for keyword in KEYWORDS:
        print(f"\n{'='*60}")
        print(f"搜索: {keyword}")
        print(f"{'='*60}")

        # 访问 Google
        print("→ 访问 Google...")
        page.goto(GOOGLE_HOME, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # 关闭 cookie 弹窗
        try:
            page.click("button:has-text('Accept all')", timeout=3000)
        except:
            pass
        try:
            page.click("button:has-text('Reject all')", timeout=2000)
        except:
            pass

        # 搜索
        print("→ 输入搜索词...")
        search_box = page.locator(GOOGLE_SEARCH_SELECTOR).first
        search_box.click()
        search_box.fill(keyword)
        search_box.press("Enter")

        # 等待结果加载
        print("→ 等待搜索结果...")
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        current_url = page.url
        print(f"→ 当前URL: {current_url[:120]}...")

        # ============================================================
        # 保存完整 HTML
        # ============================================================
        safe_name = keyword.replace('"', '').replace(' ', '_')[:40]
        html_path = DEBUG_DIR / f"serp_{safe_name}.html"
        html_content = page.content()
        html_path.write_text(html_content, encoding="utf-8")
        print(f"→ HTML 已保存: {html_path} ({len(html_content)} chars)")

        # ============================================================
        # 保存截图
        # ============================================================
        screenshot_path = DEBUG_DIR / f"serp_{safe_name}.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"→ 截图已保存: {screenshot_path}")

        # ============================================================
        # 分析 DOM 结构：尝试多种可能的选择器
        # ============================================================
        print(f"\n→ DOM 结构分析:")

        # 候选选择器
        candidates = [
            "div.g",                           # 经典 Google 结果
            "div[data-sokoban-container]",      # 新版 Google
            "div.MjjYud",                       # 另一种新版 Google
            "div.Gx5Zad",                       # 又一版
            "div[data-hveid]",                  # 通用属性
            "div.tF2Cxc",                       # 经典结果容器
            "a[jsname='UWckNb']",              # 结果链接 (jsname)
            "h3",                               # 所有标题
            "div[data-sncf]",                   # 摘要文本
            "div#search div.g",                 # search容器下的g
            "div#rso > div",                    # 结果容器
            "div#search a[href^='http']",       # 所有外部链接
        ]

        for sel in candidates:
            try:
                els = page.query_selector_all(sel)
                count = len(els)
                if count > 0:
                    # 打印第一个元素的 outerHTML (截断)
                    first_html = page.evaluate(f"""
                        (el) => el ? el.outerHTML.substring(0, 300) : 'null'
                    """, els[0] if count > 0 else None)
                    print(f"  ✓ {sel:40s} → {count:3d} 个元素  示例: {first_html[:120]}...")
                else:
                    print(f"  ✗ {sel:40s} → 0 个元素")
            except Exception as e:
                print(f"  ? {sel:40s} → 错误: {e}")

        # ============================================================
        # 深度分析：遍历 #search 下的链接
        # ============================================================
        print(f"\n→ 搜索结果链接分析 (#search 容器下):")
        links = page.query_selector_all("#search a[href^='http']")
        organic_links = []
        for link in links[:30]:
            try:
                href = link.get_attribute("href")
                text = link.inner_text().strip()
                # 排除 Google 自己的链接
                if href and not any(s in href for s in [
                    "google.com/shopping", "google.com/search",
                    "googleadservices", "google.com/preferences",
                    "google.com/advanced_search", "webcache.google",
                    "youtube.com", "google.com/maps",
                ]):
                    if text and len(text) > 5:
                        organic_links.append({"text": text[:80], "href": href[:120]})
            except:
                pass

        print(f"  有机链接数: {len(organic_links)}")
        for i, link in enumerate(organic_links[:10]):
            print(f"  [{i+1}] {link['text']}")
            print(f"      {link['href']}")

        # ============================================================
        # 查找结果容器的共同特征
        # ============================================================
        print(f"\n→ 容器特征分析:")
        # 尝试找同时包含 h3 + 链接的父容器
        containers = page.evaluate("""
            () => {
                const results = [];
                // 找所有包含 h3 和至少一个外部链接的元素
                const allDivs = document.querySelectorAll('#search div, #rso div');
                const seen = new Set();

                allDivs.forEach(div => {
                    const h3 = div.querySelector('h3');
                    const link = div.querySelector('a[href^="http"]');
                    if (h3 && link && !seen.has(div.className)) {
                        seen.add(div.className);
                        results.push({
                            tag: div.tagName,
                            className: div.className || '(none)',
                            id: div.id || '(none)',
                            hasH3: !!h3,
                            linkHref: link.href.substring(0, 80),
                        });
                    }
                });
                return results.slice(0, 20);
            }
        """)
        print(f"  找到 {len(containers)} 种不同容器类型:")
        for c in containers:
            print(f"  <{c['tag']}> class='{c['className'][:60]}' id='{c['id']}' → {c['linkHref']}")

    # 清理
    context.close()
    pw.stop()
    print(f"\n诊断完成！HTML/截图已保存到 {DEBUG_DIR}")


if __name__ == "__main__":
    main()
