"""Analytics reporting module for StudyTips AI Agent."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class AnalyticsModule:
    """Google Analytics traffic reporting and insights.

    Args:
        brain_router: BrainRouter instance.
        config: AppConfig instance.
    """

    def __init__(self, brain_router: Any, config: Any) -> None:
        self.brain = brain_router
        self.config = config

    def _ga(self) -> Any:
        from agent.integrations.google_analytics import AnalyticsClient
        return AnalyticsClient(
            property_id=self.config.google.analytics_property_id,
            service_account_key=self.config.google.service_account_key,
        )

    def get_traffic_report(self, period: str = "monthly") -> Dict[str, Any]:
        """Generate a traffic summary report.

        Args:
            period: 'daily' (7 days), 'weekly' (28 days), or 'monthly' (90 days).

        Returns:
            Traffic summary dict.
        """
        period_map = {"daily": "7daysAgo", "weekly": "28daysAgo", "monthly": "90daysAgo"}
        start_date = period_map.get(period, "28daysAgo")

        try:
            return self._ga().get_traffic_summary(start_date=start_date)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Analytics traffic report failed: %s", exc)
            return {"error": str(exc), "period": period}

    def get_top_performing_content(
        self, period: str = "monthly", limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get the best performing pages by traffic.

        Args:
            period: Time period ('daily', 'weekly', 'monthly').
            limit: Number of top pages to return.

        Returns:
            List of page performance dicts.
        """
        period_map = {"daily": "7daysAgo", "weekly": "28daysAgo", "monthly": "90daysAgo"}
        start_date = period_map.get(period, "28daysAgo")

        try:
            return self._ga().get_top_pages(start_date=start_date, limit=limit)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Top content query failed: %s", exc)
            return []

    def get_declining_content(
        self, period: str = "monthly"
    ) -> List[Dict[str, Any]]:
        """Identify content that has been losing traffic.

        Returns pages with significantly lower traffic in the recent half
        of the period compared to the first half.

        Args:
            period: Time period to analyse.

        Returns:
            List of declining page dicts.
        """
        try:
            recent = self._ga().get_top_pages(start_date="14daysAgo", limit=50)
            previous = self._ga().get_top_pages(start_date="28daysAgo", limit=50)

            recent_map = {r["pagePath"]: int(r.get("screenPageViews", 0)) for r in recent}
            declining = []
            for item in previous:
                path = item["pagePath"]
                prev_views = int(item.get("screenPageViews", 0))
                curr_views = recent_map.get(path, 0)
                if prev_views > 0 and curr_views < prev_views * 0.7:
                    declining.append({
                        "page_path": path,
                        "previous_views": prev_views,
                        "current_views": curr_views,
                        "decline_pct": round((1 - curr_views / prev_views) * 100, 1),
                    })

            return sorted(declining, key=lambda x: x["decline_pct"], reverse=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Declining content query failed: %s", exc)
            return []

    def generate_insights(self) -> str:
        """Generate actionable insights from analytics data.

        Returns:
            Formatted insights string.
        """
        try:
            top_pages = self.get_top_performing_content(limit=5)
            declining = self.get_declining_content()[:3]
            summary = self.get_traffic_report()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not fetch analytics for insights: %s", exc)
            top_pages, declining, summary = [], [], {}

        prompt = (
            "Generate actionable content and SEO insights for studytips.in based on the following analytics data.\n\n"
            f"Traffic summary: {json.dumps(summary)}\n"
            f"Top 5 pages: {json.dumps(top_pages)}\n"
            f"Declining pages: {json.dumps(declining)}\n\n"
            "Provide 5 specific, actionable recommendations to improve traffic and engagement."
        )

        brain_name = self.brain.route("analytics", priority="quality")
        return self.brain.generate(brain_name=brain_name, prompt=prompt)
