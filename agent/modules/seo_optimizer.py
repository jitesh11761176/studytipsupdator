"""SEO optimisation module for StudyTips AI Agent."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from agent.prompts.seo_prompts import (
    KEYWORD_RESEARCH_PROMPT,
    META_GENERATION_PROMPT,
    SCHEMA_GENERATION_PROMPT,
    SEO_AUDIT_PROMPT,
)

logger = logging.getLogger(__name__)


class SEOOptimizer:
    """SEO analysis and optimisation for WordPress content.

    Args:
        brain_router: BrainRouter instance.
        config: AppConfig instance.
    """

    def __init__(self, brain_router: Any, config: Any) -> None:
        self.brain = brain_router
        self.config = config

    def optimize_post(self, post_id_or_url: str) -> Dict[str, Any]:
        """Run full SEO optimisation on a post.

        Args:
            post_id_or_url: WordPress post ID or URL.

        Returns:
            Dict with meta, schema, internal links, slug suggestions.
        """
        from agent.integrations.wordpress_api import WordPressClient

        wp = WordPressClient(config=self.config.wp)

        try:
            if str(post_id_or_url).isdigit():
                post = wp.get_post(int(post_id_or_url))
            else:
                post = wp.get_post_by_url(str(post_id_or_url))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not fetch post for SEO: %s", exc)
            post = None

        title = post.get("title", {}).get("rendered", "") if post else str(post_id_or_url)
        content = post.get("content", {}).get("rendered", "") if post else ""

        meta = self.generate_meta(title, content)
        schema = self.generate_schema("article", content)

        try:
            all_posts = wp.get_posts(per_page=50)
            internal_links = self.find_internal_links(content, all_posts)
        except Exception:  # noqa: BLE001
            internal_links = []

        return {
            "post_id": post.get("id") if post else None,
            "title": title,
            "meta": meta,
            "schema": schema,
            "internal_links": internal_links,
            "status": "draft",
        }

    def generate_meta(self, title: str, content: str) -> Dict[str, str]:
        """Generate SEO meta title, description, and slug.

        Args:
            title: Post title.
            content: Post content (HTML or plain text).

        Returns:
            Dict with meta_title, meta_description, slug.
        """
        brain_name = self.brain.route("seo_optimize", priority="quality")
        raw = self.brain.generate(
            brain_name=brain_name,
            prompt=META_GENERATION_PROMPT.format(
                title=title, content=content[:2000]
            ),
        )

        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0:
                return json.loads(raw[start:end])
        except json.JSONDecodeError:
            pass

        return {"meta_title": title[:60], "meta_description": content[:155], "slug": ""}

    def generate_schema(
        self, post_type: str, content: str
    ) -> str:
        """Generate JSON-LD schema markup.

        Args:
            post_type: Schema type ('article', 'faq', 'howto').
            content: Post content to base schema on.

        Returns:
            JSON-LD schema string.
        """
        brain_name = self.brain.route("seo_optimize", priority="balanced")
        return self.brain.generate(
            brain_name=brain_name,
            prompt=SCHEMA_GENERATION_PROMPT.format(
                post_type=post_type, content=content[:3000]
            ),
        )

    def find_internal_links(
        self,
        content: str,
        existing_posts: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        """Suggest internal linking opportunities.

        Args:
            content: Post content to analyse.
            existing_posts: List of existing post objects from WordPress.

        Returns:
            List of dicts with anchor_text and target_url.
        """
        post_titles = [
            {"id": p.get("id"), "title": p.get("title", {}).get("rendered", ""), "link": p.get("link", "")}
            for p in existing_posts[:30]
        ]
        prompt = (
            "Suggest internal links for the following content.\n\n"
            f"Content excerpt:\n{content[:1500]}\n\n"
            f"Available posts to link to:\n{json.dumps(post_titles, indent=2)}\n\n"
            "Return a JSON array of objects with: anchor_text, target_url, context_sentence"
        )
        brain_name = self.brain.route("seo_optimize", priority="speed")
        raw = self.brain.generate(brain_name=brain_name, prompt=prompt)

        try:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            return json.loads(raw[start:end]) if start >= 0 else []
        except json.JSONDecodeError:
            return []

    def keyword_research(self, topic: str) -> Dict[str, Any]:
        """Research keywords for a given topic.

        Args:
            topic: Topic or seed keyword.

        Returns:
            Dict with primary_keyword, secondary_keywords, long_tail_keywords.
        """
        brain_name = self.brain.route("keyword_research", priority="quality")
        raw = self.brain.generate(
            brain_name=brain_name,
            prompt=KEYWORD_RESEARCH_PROMPT.format(topic=topic),
        )

        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0:
                return json.loads(raw[start:end])
        except json.JSONDecodeError:
            pass

        return {"primary_keyword": topic, "secondary_keywords": [], "long_tail_keywords": []}

    def audit_page_seo(self, url: str) -> Dict[str, Any]:
        """Run a single-page SEO audit.

        Args:
            url: Page URL to audit.

        Returns:
            Dict with score, issues, recommendations.
        """
        import requests as req

        try:
            response = req.get(url, timeout=15)
            html_content = response.text[:5000]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not fetch %s: %s", url, exc)
            html_content = ""

        brain_name = self.brain.route("seo_optimize", priority="quality")
        raw = self.brain.generate(
            brain_name=brain_name,
            prompt=SEO_AUDIT_PROMPT.format(url=url, content=html_content),
        )

        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0:
                return json.loads(raw[start:end])
        except json.JSONDecodeError:
            pass

        return {"url": url, "audit_result": raw, "score": None}

    def check_ranking_changes(self) -> List[Dict[str, Any]]:
        """Monitor keyword ranking changes via Search Console.

        Returns:
            List of keyword ranking change dicts.
        """
        try:
            from agent.integrations.google_search_console import SearchConsoleClient

            sc = SearchConsoleClient(
                site_url=self.config.google.search_console_site,
                service_account_key=self.config.google.service_account_key,
            )
            return sc.get_search_analytics(dimensions=["query", "page"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ranking check failed: %s", exc)
            return []

    def generate_sitemap_updates(self) -> Dict[str, Any]:
        """Generate sitemap management recommendations.

        Returns:
            Dict with sitemap URL and submission status.
        """
        sitemap_url = f"{self.config.wp.site_url}/sitemap.xml"
        try:
            from agent.integrations.google_search_console import SearchConsoleClient

            sc = SearchConsoleClient(
                site_url=self.config.google.search_console_site,
                service_account_key=self.config.google.service_account_key,
            )
            submitted = sc.submit_sitemap(sitemap_url)
            return {"sitemap_url": sitemap_url, "submitted": submitted}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sitemap submission failed: %s", exc)
            return {"sitemap_url": sitemap_url, "submitted": False, "error": str(exc)}
