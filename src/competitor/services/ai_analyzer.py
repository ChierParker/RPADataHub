"""
CompetitorWatch AI analysis service
- Encapsulates DeepSeek API calls (reuses RPADataHub API call pattern)
- Pricing strategy analysis (daily / weekly reports)
- Anomaly detection alerts (price spike, ad placement change, new competitor low-price entry)
- Natural language report generation

API Key loaded from environment via unified config center.
"""

import json
import time
import traceback
from datetime import datetime, timedelta
from typing import Optional

import requests

from config.settings import get_config
from logger_config import setup_logger

logger = setup_logger("AIAnalyzer")


class AIAnalyzer:
    """
    AI competitor analyzer

    Functions:
        - Daily report: analyze daily price changes, ranking changes, ad placement changes
        - Weekly report: comprehensive weekly trend & strategy analysis
        - Anomaly detection: identify price spikes, ad placement changes, new competitor entry etc.
    """

    def __init__(self, api_key: str = None, api_url: str = None, model: str = None):
        """
        Initialize AI analyzer

        Parameters:
            api_key: DeepSeek API Key (reads from config if not provided)
            api_url: API endpoint URL
            model: model name
        """
        cfg = get_config()
        self.api_key = api_key or cfg.ai.api_key
        self.api_url = api_url or cfg.ai.api_url
        self.model = model or cfg.ai.model

        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY not set; AI functions will be unavailable")
        elif "your-" in self.api_key.lower() or "placeholder" in self.api_key.lower():
            logger.warning("DEEPSEEK_API_KEY is still a placeholder; AI functions will be unavailable")

    # ============================================================
    # Report generation
    # ============================================================

    def generate_daily_report(self, competitor_name: str, platform: str,
                               trend_data: list, snapshots: list) -> dict:
        """
        Generate competitor daily report

        Parameters:
            competitor_name: competitor name
            platform: platform name
            trend_data: DW daily aggregate trend data (recent days)
            snapshots: daily snapshot details

        Returns:
            dict: {"content": str, "summary": str, "alert_level": str}
        """
        prompt = self._build_daily_prompt(competitor_name, platform, trend_data, snapshots)
        response = self._call_api(prompt)
        return self._parse_report_response(response, "daily")

    def generate_weekly_report(self, competitor_name: str, platform: str,
                                trend_data: list, competitors_context: str = "") -> dict:
        """
        Generate competitor weekly report

        Parameters:
            competitor_name: competitor name
            platform: platform name
            trend_data: DW daily aggregate trend (recent 14 days)
            competitors_context: context info about similar competitors

        Returns:
            dict: {"content": str, "summary": str, "alert_level": str}
        """
        prompt = self._build_weekly_prompt(
            competitor_name, platform, trend_data, competitors_context
        )
        response = self._call_api(prompt)
        return self._parse_report_response(response, "weekly")

    def detect_anomaly(self, competitor_name: str, platform: str,
                       recent_data: list, historical_baseline: dict = None) -> dict:
        """
        Anomaly detection and instant alert

        Detection dimensions:
            - Single price drop > 20%
            - Sudden ad placement occupation
            - New competitor pricing below market by 30%
            - Ranking spike volatility

        Parameters:
            competitor_name: competitor name
            platform: platform name
            recent_data: recent collection data
            historical_baseline: historical baseline (avg price, avg rank etc.)

        Returns:
            dict: {
                "has_anomaly": bool,
                "anomalies": [{"type": str, "severity": str, "description": str}],
                "content": str,  # AI-generated anomaly report
            }
        """
        # Phase 1: Rule-based quick detection (no API needed)
        rule_anomalies = self._rule_based_detection(
            competitor_name, recent_data, historical_baseline or {}
        )

        content = ""
        has_anomaly = len(rule_anomalies) > 0

        # Phase 2: AI deep analysis (if anomalies detected)
        if rule_anomalies:
            anomaly_desc = "\n".join([
                f"- [{a['severity']}] {a['type']}: {a['description']}"
                for a in rule_anomalies
            ])
            prompt = self._build_anomaly_prompt(
                competitor_name, platform, anomaly_desc, recent_data
            )
            content = self._call_api(prompt) or ""

        return {
            "has_anomaly": has_anomaly,
            "anomalies": rule_anomalies,
            "content": content,
        }

    # ============================================================
    # Prompt construction
    # ============================================================

    def _build_daily_prompt(self, competitor_name: str, platform: str,
                             trend_data: list, snapshots: list) -> str:
        """Build daily report analysis prompt"""
        trend_summary = json.dumps(trend_data[-7:] if trend_data else [], ensure_ascii=False, indent=2, default=str)
        snap_summary = json.dumps(snapshots[:5] if snapshots else [], ensure_ascii=False, indent=2, default=str)

        return f"""You are an e-commerce competitive intelligence analyst. Analyze the following competitor data and generate a concise daily report in Chinese.

Competitor: {competitor_name}
Platform: {platform}

Recent 7-day price trend:
{trend_summary}

Today's snapshot highlights:
{snap_summary}

Please provide:
1. **Headline Summary** (one sentence)
2. **Price Analysis**: current price vs recent trend, any significant changes
3. **Ranking Analysis**: ranking changes and implications
4. **Ad Placement**: any ad strategy changes observed
5. **Actionable Insights**: 2-3 concrete suggestions

Format in Markdown. Keep it concise (under 300 words)."""

    def _build_weekly_prompt(self, competitor_name: str, platform: str,
                              trend_data: list, competitors_context: str) -> str:
        """Build weekly report analysis prompt"""
        trend_summary = json.dumps(trend_data, ensure_ascii=False, indent=2)

        return f"""You are an e-commerce competitive intelligence analyst. Generate a weekly strategy report in Chinese.

Competitor: {competitor_name}
Platform: {platform}
Context on related competitors: {competitors_context or 'N/A'}

14-day daily trend data:
{trend_summary}

Please provide:
1. **Executive Summary** (2-3 sentences)
2. **Price Strategy Assessment**: weekly trend, pricing pattern, discount rhythm
3. **Market Position**: ranking trajectory, market share signals
4. **Promotion/Ad Strategy**: observed campaign patterns
5. **Risk Assessment**: potential threats or competitive moves
6. **Next Week Recommendations**: 3-4 prioritized actions

Format in Markdown. Comprehensive but not verbose."""

    def _build_anomaly_prompt(self, competitor_name: str, platform: str,
                               anomaly_desc: str, recent_data: list) -> str:
        """Build anomaly alert analysis prompt"""
        data_summary = json.dumps(recent_data[-3:] if recent_data else [], ensure_ascii=False, indent=2)

        return f"""You are an e-commerce anomaly detection analyst. Analyze the following alert in Chinese.

Competitor: {competitor_name}  |  Platform: {platform}

Detected Anomalies:
{anomaly_desc}

Recent snapshot data:
{data_summary}

Please provide:
1. **Severity Assessment**: how critical is this
2. **Root Cause Analysis**: likely reasons
3. **Impact Forecast**: potential market impact
4. **Response Recommendation**: immediate actions to take

Be concise and actionable. Under 200 words."""

    # ============================================================
    # API call
    # ============================================================

    def _call_api(self, prompt: str, max_retries: int = 2) -> Optional[str]:
        """
        Call DeepSeek Chat API

        Parameters:
            prompt: user prompt
            max_retries: max retry count

        Returns:
            str or None: AI response text
        """
        if not self.api_key or "your-" in self.api_key.lower():
            logger.warning("DEEPSEEK_API_KEY not configured; skipping API call")
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an e-commerce competitive analysis expert. Always respond in Chinese."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 2048,
            "temperature": 0.7,
        }

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                resp = requests.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=60,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "")
                    logger.warning("[AI API] Empty response choices")
                    return None
                elif resp.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning(f"[AI API] Rate limited (429), retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    logger.error(f"[AI API] HTTP {resp.status_code}: {resp.text[:200]}")
                    last_error = f"HTTP {resp.status_code}"
            except requests.Timeout:
                logger.warning(f"[AI API] Timeout, attempt {attempt + 1}/{max_retries + 1}")
                last_error = "Timeout"
            except Exception as e:
                logger.error(f"[AI API] Exception: {e}")
                last_error = str(e)

        logger.error(f"[AI API] All {max_retries + 1} attempts failed: {last_error}")
        return None

    # ============================================================
    # Response parsing
    # ============================================================

    def _parse_report_response(self, response: Optional[str],
                                 report_type: str) -> dict:
        """Parse AI report response"""
        if not response:
            return {
                "content": f"AI analysis unavailable (API not configured or call failed)",
                "summary": f"{report_type} report generation failed",
                "alert_level": "info",
            }

        # Extract first line as summary
        summary = ""
        for line in response.split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                summary = line[:100]
                break

        # Determine alert level
        alert_level = "info"
        lower_text = response.lower()
        if any(w in lower_text for w in ["drop", "anomaly", "surge", "spike", "risk", "warning",
                                          "降价", "异常", "激增", "突变", "风险", "警告"]):
            alert_level = "warning"
        if any(w in lower_text for w in ["severe", "urgent", "price war tier", "crash", "cut-throat",
                                          "严重", "紧急", "价格战级别", "断崖", "腰斩"]):
            alert_level = "critical"

        return {
            "content": response,
            "summary": summary or "Analysis complete",
            "alert_level": alert_level,
        }

    def _parse_anomaly_response(self, response: Optional[str]) -> dict:
        """Parse anomaly detection API response"""
        if not response:
            return {"has_anomaly": False, "anomalies": [], "content": ""}

        has_anomaly = "[ALERT]" in response
        return {
            "has_anomaly": has_anomaly,
            "anomalies": [],
            "content": response,
        }

    # ============================================================
    # Rule engine (no API required, quick initial scan)
    # ============================================================

    def _rule_based_detection(self, competitor_name: str,
                               recent_data: list,
                               baseline: dict) -> list:
        """
        Rule-based price anomaly detection (no AI API needed)

        Detection rules:
            1. Single price drop > 20%
            2. Price below historical avg by 30%
            3. Ranking change > 50 positions
            4. New ad placement emergence
        """
        anomalies = []
        if not recent_data:
            return anomalies

        latest = recent_data[-1] if recent_data else {}
        current_price = latest.get("current_price")
        original_price = latest.get("original_price")

        # Rule 1: price vs original price drop
        if current_price and original_price and original_price > 0:
            drop_pct = (original_price - current_price) / original_price * 100
            if drop_pct > 20:
                anomalies.append({
                    "type": "price_drop",
                    "severity": "warning" if drop_pct < 40 else "critical",
                    "description": (
                        f"Price single drop {drop_pct:.1f}%: "
                        f"Original ${original_price:.2f} -> Current ${current_price:.2f}"
                    ),
                })

        # Rule 2: vs historical baseline
        if baseline and current_price:
            hist_avg = baseline.get("avg_price")
            if hist_avg and hist_avg > 0:
                deviation = (current_price - hist_avg) / hist_avg * 100
                if deviation < -30:
                    anomalies.append({
                        "type": "price_below_baseline",
                        "severity": "critical",
                        "description": (
                            f"Price below historical avg by {abs(deviation):.1f}%: "
                            f"Current ${current_price:.2f} vs Avg ${hist_avg:.2f}"
                        ),
                    })

        # Rule 3: ranking volatility
        if recent_data and len(recent_data) >= 2:
            prev_rank = recent_data[-2].get("rank_position")
            curr_rank = latest.get("rank_position")
            if prev_rank and curr_rank:
                rank_change = abs(curr_rank - prev_rank)
                if rank_change > 50:
                    anomalies.append({
                        "type": "rank_volatility",
                        "severity": "warning" if rank_change < 100 else "critical",
                        "description": (
                            f"Rank spike: {prev_rank} -> {curr_rank} (change {rank_change})"
                        ),
                    })

        # Rule 4: ad placement emergence
        if recent_data and len(recent_data) >= 2:
            prev_ad = recent_data[-2].get("is_ad", 0)
            curr_ad = latest.get("is_ad", 0)
            if prev_ad == 0 and curr_ad == 1:
                anomalies.append({
                    "type": "ad_placement_emerged",
                    "severity": "warning",
                    "description": "Competitor suddenly occupies ad placement (previously no ad spend)",
                })

        if anomalies:
            logger.info(
                f"[Rule Engine] {competitor_name}: detected {len(anomalies)} anomalies"
            )

        return anomalies
