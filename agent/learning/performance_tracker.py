"""Performance tracking for published content."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agent.core.memory import AgentMemory

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """Track and analyse content performance metrics over time.

    Args:
        memory: AgentMemory instance.
    """

    def __init__(self, memory: AgentMemory) -> None:
        self.memory = memory

    def track_post(
        self,
        post_id: str,
        url: str = "",
        keywords: Optional[List[str]] = None,
    ) -> None:
        """Start tracking a post's performance.

        Args:
            post_id: WordPress post ID.
            url: Post URL.
            keywords: Target keywords to monitor.
        """
        self.memory.update_content_performance(
            post_id=post_id,
            metrics={
                "url": url,
                "keywords": ", ".join(keywords or []),
                "views": 0,
                "position": 0,
                "bounce_rate": 0,
            },
        )
        logger.info("Started tracking post %s: %s", post_id, url)

    def update_metrics(
        self,
        post_id: str,
        views: int = 0,
        position: float = 0,
        bounce_rate: float = 0,
    ) -> None:
        """Update performance metrics for a tracked post.

        Args:
            post_id: WordPress post ID.
            views: Total page views.
            position: Average search ranking position.
            bounce_rate: Bounce rate (0–1).
        """
        self.memory.update_content_performance(
            post_id=post_id,
            metrics={
                "views": views,
                "position": position,
                "bounce_rate": bounce_rate,
            },
        )

    def get_best_performing_strategies(self) -> List[Dict[str, Any]]:
        """Analyse tracked content to identify top performing strategies.

        Returns:
            List of winning strategy dicts.
        """
        return self.memory.get_winning_strategies("content")

    def get_performance_trends(
        self, post_id: str
    ) -> Dict[str, Any]:
        """Get performance history for a specific post.

        Args:
            post_id: WordPress post ID.

        Returns:
            Performance data dict.
        """
        with self.memory._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM content_performance WHERE post_id = ?",
                (post_id,),
            ).fetchone()
        if row:
            return dict(row)
        return {"post_id": post_id, "status": "not_tracked"}

    def get_all_tracked_posts(self) -> List[Dict[str, Any]]:
        """Return all tracked posts with their current metrics.

        Returns:
            List of performance data dicts.
        """
        with self.memory._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM content_performance ORDER BY views DESC"
            ).fetchall()
        return [dict(row) for row in rows]
