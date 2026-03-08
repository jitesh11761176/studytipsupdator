"""Google Search Console API client."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SearchConsoleClient:
    """Google Search Console API wrapper.

    Requires a Google service account with Search Console access, or OAuth2
    credentials. The service account key JSON path is set via
    GOOGLE_SERVICE_ACCOUNT_KEY environment variable.

    Args:
        site_url: The verified site URL in Search Console.
        service_account_key: Path to service account JSON key file.
    """

    def __init__(self, site_url: str, service_account_key: str = "") -> None:
        self.site_url = site_url
        self.service_account_key = service_account_key
        self._service: Optional[Any] = None

    def _get_service(self) -> Any:
        """Lazily initialise the Search Console API service."""
        if self._service is not None:
            return self._service

        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        if self.service_account_key:
            creds = service_account.Credentials.from_service_account_file(
                self.service_account_key,
                scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
            )
        else:
            # Fall back to application default credentials
            import google.auth
            creds, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
            )

        self._service = build("searchconsole", "v1", credentials=creds)
        return self._service

    def get_search_analytics(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        dimensions: Optional[List[str]] = None,
        row_limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Retrieve search analytics data.

        Args:
            start_date: Start date in YYYY-MM-DD format.
            end_date: End date in YYYY-MM-DD format.
            dimensions: Dimensions to group by (e.g. ['query', 'page']).
            row_limit: Maximum number of rows to return.

        Returns:
            List of result rows.
        """
        if start_date is None:
            start_date = (date.today() - timedelta(days=28)).isoformat()
        if end_date is None:
            end_date = date.today().isoformat()
        if dimensions is None:
            dimensions = ["query", "page"]

        body = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": dimensions,
            "rowLimit": row_limit,
        }
        response = (
            self._get_service()
            .searchanalytics()
            .query(siteUrl=self.site_url, body=body)
            .execute()
        )
        return response.get("rows", [])

    def get_ranking_keywords(self, url: str) -> List[Dict[str, Any]]:
        """Get ranking keywords for a specific URL.

        Args:
            url: Full page URL to query.

        Returns:
            List of keyword rows with clicks, impressions, position.
        """
        return self.get_search_analytics(
            dimensions=["query"],
            row_limit=50,
        )

    def submit_sitemap(self, sitemap_url: str) -> bool:
        """Submit a sitemap to Google Search Console.

        Args:
            sitemap_url: Full URL of the sitemap.xml.

        Returns:
            True on success.
        """
        self._get_service().sitemaps().submit(
            siteUrl=self.site_url, feedpath=sitemap_url
        ).execute()
        logger.info("Sitemap submitted: %s", sitemap_url)
        return True

    def request_indexing(self, url: str) -> bool:
        """Request indexing for a URL via the Indexing API.

        Note: Uses the Google Indexing API, not Search Console directly.

        Args:
            url: Page URL to request indexing for.

        Returns:
            True on success.
        """
        from googleapiclient.discovery import build
        from google.oauth2 import service_account

        if not self.service_account_key:
            logger.warning("No service account key for Indexing API")
            return False

        creds = service_account.Credentials.from_service_account_file(
            self.service_account_key,
            scopes=["https://www.googleapis.com/auth/indexing"],
        )
        service = build("indexing", "v3", credentials=creds)
        body = {"url": url, "type": "URL_UPDATED"}
        service.urlNotifications().publish(body=body).execute()
        logger.info("Indexing requested for: %s", url)
        return True
