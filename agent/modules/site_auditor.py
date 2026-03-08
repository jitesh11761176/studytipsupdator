"""Site audit module for StudyTips AI Agent."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger(__name__)


class SiteAuditor:
    """Comprehensive site health and SEO auditor.

    Args:
        config: AppConfig instance.
    """

    def __init__(self, config: Any) -> None:
        self.config = config

    def _wp(self) -> Any:
        from agent.integrations.wordpress_api import WordPressClient
        return WordPressClient(config=self.config.wp)

    def full_audit(self) -> Dict[str, Any]:
        """Run a comprehensive site audit.

        Returns:
            Dict with critical, warning, and good issue lists.
        """
        critical = []
        warnings = []
        good = []

        # Broken links
        try:
            broken = self.find_broken_links()
            if broken:
                critical.append({"issue": "Broken links found", "count": len(broken), "items": broken[:5]})
            else:
                good.append("No broken links detected")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Could not check broken links: {exc}")

        # Missing meta
        try:
            missing_meta = self.find_missing_meta()
            if missing_meta:
                warnings.append({"issue": "Missing meta descriptions", "count": len(missing_meta), "items": missing_meta[:5]})
            else:
                good.append("All pages have meta descriptions")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Could not check meta descriptions: {exc}")

        # Thin content
        try:
            thin = self.find_thin_content(min_words=300)
            if thin:
                warnings.append({"issue": "Thin content pages", "count": len(thin), "items": thin[:5]})
            else:
                good.append("No thin content detected")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Could not check content length: {exc}")

        # Missing alt texts
        try:
            missing_alts = self.find_missing_alt_texts()
            if missing_alts:
                warnings.append({"issue": "Images missing alt text", "count": len(missing_alts)})
            else:
                good.append("All images have alt text")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Could not check alt texts: {exc}")

        return {
            "critical": critical,
            "warnings": warnings,
            "good": good,
            "score": max(0, 100 - len(critical) * 20 - len(warnings) * 5),
        }

    def find_broken_links(self) -> List[Dict[str, str]]:
        """Scan for broken internal and external links.

        Returns:
            List of dicts with page_url and broken_link.
        """
        broken = []
        try:
            posts = self._wp().get_posts(per_page=20)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not fetch posts for link check: %s", exc)
            return []

        for post in posts:
            content = post.get("content", {}).get("rendered", "")
            page_url = post.get("link", "")
            links = re.findall(r'href=["\']([^"\']+)["\']', content)

            for link in links:
                if link.startswith(("#", "mailto:", "tel:", "javascript:")):
                    continue
                try:
                    resp = requests.head(link, timeout=5, allow_redirects=True)
                    if resp.status_code >= 400:
                        broken.append({"page_url": page_url, "broken_link": link, "status": resp.status_code})
                except Exception:  # noqa: BLE001
                    broken.append({"page_url": page_url, "broken_link": link, "status": "timeout"})

        return broken

    def find_missing_meta(self) -> List[Dict[str, str]]:
        """Find posts and pages missing meta descriptions.

        Returns:
            List of dicts with post id, title, and link.
        """
        missing = []
        try:
            posts = self._wp().get_posts(per_page=50)
            pages = self._wp().get_pages(per_page=50)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not fetch content for meta check: %s", exc)
            return []

        for item in posts + pages:
            meta = item.get("meta", {}) or {}
            yoast_desc = (
                meta.get("_yoast_wpseo_metadesc", "")
                or meta.get("rank_math_description", "")
                or item.get("excerpt", {}).get("rendered", "")
            )
            if not yoast_desc or yoast_desc.strip() in ("", "<p></p>", "<p></p>\n"):
                missing.append({
                    "id": str(item.get("id", "")),
                    "title": item.get("title", {}).get("rendered", ""),
                    "link": item.get("link", ""),
                })
        return missing

    def find_missing_alt_texts(self) -> List[Dict[str, str]]:
        """Find all images in published content that lack alt text.

        Returns:
            List of image src strings.
        """
        missing = []
        try:
            posts = self._wp().get_posts(per_page=50)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not fetch posts for alt text check: %s", exc)
            return []

        for post in posts:
            content = post.get("content", {}).get("rendered", "")
            img_tags = re.findall(r'<img[^>]+>', content)
            for img in img_tags:
                alt_match = re.search(r'alt=["\']([^"\']*)["\']', img)
                if not alt_match or not alt_match.group(1).strip():
                    src_match = re.search(r'src=["\']([^"\']+)["\']', img)
                    src = src_match.group(1) if src_match else "unknown"
                    missing.append({"post_id": str(post.get("id", "")), "src": src})

        return missing

    def check_page_speed(self) -> Dict[str, Any]:
        """Basic page speed check using response time.

        Returns:
            Dict with load_time_ms and recommendations.
        """
        site_url = self.config.wp.site_url
        try:
            import time
            start = time.time()
            resp = requests.get(site_url, timeout=15)
            elapsed_ms = round((time.time() - start) * 1000)
            content_size = len(resp.content)
            status = "good" if elapsed_ms < 2000 else "needs_improvement" if elapsed_ms < 4000 else "slow"
            return {
                "url": site_url,
                "load_time_ms": elapsed_ms,
                "content_size_kb": round(content_size / 1024, 1),
                "status": status,
                "http_status": resp.status_code,
            }
        except Exception as exc:  # noqa: BLE001
            return {"url": site_url, "error": str(exc)}

    def find_thin_content(self, min_words: int = 300) -> List[Dict[str, Any]]:
        """Find posts with low word count.

        Args:
            min_words: Minimum acceptable word count.

        Returns:
            List of dicts with post id, title, and word count.
        """
        thin = []
        try:
            posts = self._wp().get_posts(per_page=100)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not fetch posts for thin content check: %s", exc)
            return []

        for post in posts:
            content = post.get("content", {}).get("rendered", "")
            # Strip HTML tags for word count
            plain = re.sub(r'<[^>]+>', ' ', content)
            word_count = len(plain.split())
            if word_count < min_words:
                thin.append({
                    "id": post.get("id"),
                    "title": post.get("title", {}).get("rendered", ""),
                    "word_count": word_count,
                    "link": post.get("link", ""),
                })

        return sorted(thin, key=lambda x: x["word_count"])

    def find_duplicate_content(self) -> List[Dict[str, Any]]:
        """Detect posts with very similar titles that may be duplicates.

        Returns:
            List of potential duplicate pairs.
        """
        try:
            posts = self._wp().get_posts(per_page=100)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not fetch posts for duplicate check: %s", exc)
            return []

        titles = [(p.get("id"), p.get("title", {}).get("rendered", ""), p.get("link", "")) for p in posts]
        duplicates = []
        seen: list = []
        for post_id, title, link in titles:
            title_lower = title.lower().strip()
            for seen_id, seen_title, seen_link in seen:
                # Simple similarity: shared words > 70% overlap
                t1_words = set(title_lower.split())
                t2_words = set(seen_title.lower().split())
                if t1_words and t2_words:
                    overlap = len(t1_words & t2_words) / max(len(t1_words), len(t2_words))
                    if overlap > 0.7:
                        duplicates.append({
                            "post1": {"id": seen_id, "title": seen_title, "link": seen_link},
                            "post2": {"id": post_id, "title": title, "link": link},
                            "similarity": round(overlap, 2),
                        })
            seen.append((post_id, title, link))

        return duplicates

    def generate_audit_report(self) -> str:
        """Generate a formatted audit report string.

        Returns:
            Formatted text report.
        """
        audit = self.full_audit()
        lines = [
            "🔍 **Site Audit Report — studytips.in**",
            "",
            f"Overall Score: {audit.get('score', 'N/A')}/100",
            "",
        ]

        if audit.get("critical"):
            lines.append("🔴 **Critical Issues:**")
            for issue in audit["critical"]:
                if isinstance(issue, dict):
                    lines.append(f"  • {issue.get('issue', issue)} ({issue.get('count', '')})")
                else:
                    lines.append(f"  • {issue}")

        if audit.get("warnings"):
            lines.append("\n⚠️  **Warnings:**")
            for w in audit["warnings"]:
                if isinstance(w, dict):
                    lines.append(f"  • {w.get('issue', w)} ({w.get('count', '')})")
                else:
                    lines.append(f"  • {w}")

        if audit.get("good"):
            lines.append("\n✅ **Good:**")
            for g in audit["good"]:
                lines.append(f"  • {g}")

        return "\n".join(lines)
