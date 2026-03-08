"""Google Analytics GA4 API client."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AnalyticsClient:
    """Google Analytics GA4 Data API wrapper.

    Args:
        property_id: GA4 property ID (numeric, e.g. '123456789').
        service_account_key: Path to service account JSON key file.
    """

    def __init__(self, property_id: str, service_account_key: str = "") -> None:
        self.property_id = property_id
        self.service_account_key = service_account_key
        self._client: Optional[Any] = None

    def _get_client(self) -> Any:
        """Lazily initialise the GA4 Data API client."""
        if self._client is not None:
            return self._client

        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.oauth2 import service_account

        if self.service_account_key:
            creds = service_account.Credentials.from_service_account_file(
                self.service_account_key,
                scopes=["https://www.googleapis.com/auth/analytics.readonly"],
            )
            self._client = BetaAnalyticsDataClient(credentials=creds)
        else:
            self._client = BetaAnalyticsDataClient()

        return self._client

    def _run_report(
        self,
        dimensions: List[str],
        metrics: List[str],
        start_date: str,
        end_date: str,
        dimension_filter: Optional[Any] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Execute a GA4 RunReport request.

        Args:
            dimensions: List of dimension names.
            metrics: List of metric names.
            start_date: YYYY-MM-DD or relative (e.g. '7daysAgo').
            end_date: YYYY-MM-DD or 'today'.
            dimension_filter: Optional FilterExpression.
            limit: Maximum rows.

        Returns:
            List of row dicts.
        """
        from google.analytics.data_v1beta.types import (
            DateRange,
            Dimension,
            Metric,
            RunReportRequest,
        )

        request = RunReportRequest(
            property=f"properties/{self.property_id}",
            dimensions=[Dimension(name=d) for d in dimensions],
            metrics=[Metric(name=m) for m in metrics],
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            limit=limit,
        )
        if dimension_filter:
            request.dimension_filter = dimension_filter

        response = self._get_client().run_report(request)
        rows = []
        for row in response.rows:
            row_dict: Dict[str, Any] = {}
            for i, dim in enumerate(dimensions):
                row_dict[dim] = row.dimension_values[i].value
            for i, met in enumerate(metrics):
                row_dict[met] = row.metric_values[i].value
            rows.append(row_dict)
        return rows

    def get_page_views(
        self,
        start_date: str = "28daysAgo",
        end_date: str = "today",
        page_path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get page view metrics.

        Args:
            start_date: Start date or relative string.
            end_date: End date or 'today'.
            page_path: Filter to a specific page path.

        Returns:
            List of rows with pagePath and screenPageViews.
        """
        filter_expr = None
        if page_path:
            from google.analytics.data_v1beta.types import (
                DimensionFilter,
                Filter,
                FilterExpression,
            )
            filter_expr = FilterExpression(
                filter=DimensionFilter(
                    field_name="pagePath",
                    string_filter=Filter.StringFilter(value=page_path),
                )
            )

        return self._run_report(
            dimensions=["pagePath"],
            metrics=["screenPageViews", "sessions", "bounceRate"],
            start_date=start_date,
            end_date=end_date,
            dimension_filter=filter_expr,
        )

    def get_traffic_summary(
        self,
        start_date: str = "28daysAgo",
        end_date: str = "today",
    ) -> Dict[str, Any]:
        """Get overall traffic summary.

        Args:
            start_date: Start date.
            end_date: End date.

        Returns:
            Dict with total sessions, users, page views, bounce rate.
        """
        rows = self._run_report(
            dimensions=["date"],
            metrics=["sessions", "totalUsers", "screenPageViews", "bounceRate"],
            start_date=start_date,
            end_date=end_date,
            limit=400,
        )
        total_sessions = sum(int(r.get("sessions", 0)) for r in rows)
        total_users = sum(int(r.get("totalUsers", 0)) for r in rows)
        total_views = sum(int(r.get("screenPageViews", 0)) for r in rows)
        avg_bounce = (
            sum(float(r.get("bounceRate", 0)) for r in rows) / len(rows)
            if rows
            else 0.0
        )
        return {
            "sessions": total_sessions,
            "users": total_users,
            "page_views": total_views,
            "avg_bounce_rate": round(avg_bounce, 4),
            "daily_rows": rows,
        }

    def get_top_pages(
        self,
        start_date: str = "28daysAgo",
        end_date: str = "today",
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get top performing pages by page views.

        Args:
            start_date: Start date.
            end_date: End date.
            limit: Maximum pages to return.

        Returns:
            List of dicts sorted by page views descending.
        """
        return self._run_report(
            dimensions=["pagePath", "pageTitle"],
            metrics=["screenPageViews", "sessions", "bounceRate"],
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    def get_bounce_rate(
        self,
        page_path: str,
        start_date: str = "28daysAgo",
        end_date: str = "today",
    ) -> float:
        """Get the bounce rate for a specific page.

        Args:
            page_path: Page path to check.
            start_date: Start date.
            end_date: End date.

        Returns:
            Bounce rate as a float (0–1).
        """
        rows = self.get_page_views(
            start_date=start_date,
            end_date=end_date,
            page_path=page_path,
        )
        if rows:
            return float(rows[0].get("bounceRate", 0))
        return 0.0
