"""Navigation and category management module for StudyTips AI Agent."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class NavigationManager:
    """WordPress navigation menu and category hierarchy management.

    Args:
        brain_router: BrainRouter instance.
        config: AppConfig instance.
    """

    def __init__(self, brain_router: Any, config: Any) -> None:
        self.brain = brain_router
        self.config = config

    def _wp(self) -> Any:
        from agent.integrations.wordpress_api import WordPressClient
        return WordPressClient(config=self.config.wp)

    def get_menu_structure(self) -> Dict[str, Any]:
        """Retrieve the current navigation menu hierarchy.

        Returns:
            Dict with menus list and their items.
        """
        try:
            # Standard WP REST API doesn't expose menus without a plugin;
            # fall back to fetching pages as a proxy for navigation structure
            pages = self._wp().get_pages(per_page=100)
            categories = self._wp().get_all_categories()

            return {
                "pages": [
                    {
                        "id": p.get("id"),
                        "title": p.get("title", {}).get("rendered", ""),
                        "parent": p.get("parent", 0),
                        "link": p.get("link", ""),
                        "menu_order": p.get("menu_order", 0),
                    }
                    for p in pages
                ],
                "categories": [
                    {"id": c.get("id"), "name": c.get("name", ""), "parent": c.get("parent", 0), "count": c.get("count", 0)}
                    for c in categories
                ],
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not fetch menu structure: %s", exc)
            return {"pages": [], "categories": []}

    def add_page_to_menu(
        self,
        page_id: int,
        menu_location: str = "primary",
        parent_item: int = 0,
    ) -> Dict[str, Any]:
        """Add a page to the navigation menu.

        Args:
            page_id: WordPress page ID to add.
            menu_location: Menu location slug (e.g. 'primary', 'footer').
            parent_item: Parent menu item ID (0 = top level).

        Returns:
            Result dict.
        """
        logger.info("Adding page %d to menu '%s' under parent %d", page_id, menu_location, parent_item)
        # WP REST API requires the WP REST API Menus plugin for direct menu manipulation.
        # Return a structured action for human review.
        return {
            "action": "add_to_menu",
            "page_id": page_id,
            "menu_location": menu_location,
            "parent_item": parent_item,
            "status": "pending_approval",
            "note": "Apply via WP Admin > Appearance > Menus or using WP-CLI",
        }

    def reorganize_categories(
        self, suggestions: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Generate category reorganisation suggestions.

        Args:
            suggestions: Optional pre-computed suggestions to apply.

        Returns:
            Dict with category reorganisation plan.
        """
        if suggestions:
            return {"suggestions": suggestions, "status": "pending_approval"}

        categories = self._wp().get_all_categories()
        cat_list = [
            {"id": c.get("id"), "name": c.get("name", ""), "parent": c.get("parent", 0), "count": c.get("count", 0)}
            for c in categories
        ]

        prompt = (
            "Analyse the following WordPress category structure for studytips.in and suggest improvements.\n\n"
            f"Categories:\n{json.dumps(cat_list, indent=2)}\n\n"
            "Suggest a better hierarchy for an educational site. "
            "Return JSON with: issues (list) and reorganization_plan (list of {id, name, suggested_parent, reason})."
        )

        brain_name = self.brain.route("site_audit", priority="balanced")
        raw = self.brain.generate(brain_name=brain_name, prompt=prompt)

        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            return json.loads(raw[start:end]) if start >= 0 else {"raw": raw}
        except json.JSONDecodeError:
            return {"raw": raw}

    def suggest_menu_placement(
        self, page_title: str, page_content: str = ""
    ) -> str:
        """Suggest where a new page should be placed in navigation.

        Args:
            page_title: Title of the new page.
            page_content: Content snippet for context.

        Returns:
            Recommendation string.
        """
        structure = self.get_menu_structure()
        existing_pages = [p["title"] for p in structure.get("pages", [])[:20]]

        prompt = (
            f"Suggest where to place the page '{page_title}' in the navigation menu of studytips.in.\n\n"
            f"Content preview: {page_content[:500]}\n\n"
            f"Existing pages: {existing_pages}\n\n"
            "Recommend: menu location (primary/footer), parent page (if applicable), and reasoning."
        )

        brain_name = self.brain.route("general", priority="speed")
        return self.brain.generate(brain_name=brain_name, prompt=prompt)

    def suggest_pages_to_link(self, content: str) -> List[Dict[str, Any]]:
        """Analyse content and suggest which existing pages to link to.

        Args:
            content: Post or page content to analyse.

        Returns:
            List of dicts with keys: page_title, url, anchor_text, reason.
        """
        structure = self.get_menu_structure()
        existing_pages = [
            {"title": p["title"], "url": p["link"]}
            for p in structure.get("pages", [])[:30]
        ]
        categories = [
            {"name": c["name"]}
            for c in structure.get("categories", [])[:20]
        ]

        prompt = (
            "Analyse the following content and suggest which existing pages or categories of "
            "studytips.in would be relevant to link to from within this content. "
            "Return ONLY a valid JSON array of objects with keys: "
            "page_title, url, anchor_text, reason.\n\n"
            f"Existing pages: {json.dumps(existing_pages)}\n"
            f"Categories: {json.dumps(categories)}\n\n"
            f"Content:\n{content[:3000]}"
        )

        try:
            brain_name = self.brain.route("seo_optimize", priority="balanced")
            raw = self.brain.generate(brain_name=brain_name, prompt=prompt)
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start >= 0:
                return json.loads(raw[start:end])
        except Exception as exc:  # noqa: BLE001
            logger.warning("suggest_pages_to_link failed: %s", exc)
        return []

    def suggest_new_pages(self, content: str) -> List[Dict[str, Any]]:
        """Identify topics in content that don't have dedicated pages yet.

        Args:
            content: Post or page content to analyse.

        Returns:
            List of dicts with keys: topic, suggested_title, suggested_slug, reason.
        """
        structure = self.get_menu_structure()
        existing_titles = [p["title"] for p in structure.get("pages", [])]

        prompt = (
            "Identify topics mentioned in the following content that studytips.in does NOT yet "
            "have dedicated pages for, and suggest creating new pages for them. "
            "Return ONLY a valid JSON array of objects with keys: "
            "topic, suggested_title, suggested_slug, reason.\n\n"
            f"Existing page titles: {json.dumps(existing_titles)}\n\n"
            f"Content:\n{content[:3000]}"
        )

        try:
            brain_name = self.brain.route("content_plan", priority="balanced")
            raw = self.brain.generate(brain_name=brain_name, prompt=prompt)
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start >= 0:
                return json.loads(raw[start:end])
        except Exception as exc:  # noqa: BLE001
            logger.warning("suggest_new_pages failed: %s", exc)
        return []

    def find_orphan_pages(self) -> List[Dict[str, Any]]:
        """Find pages that have no internal links pointing to them.

        Returns:
            List of dicts with keys: id, title, url.
        """
        try:
            from bs4 import BeautifulSoup

            structure = self.get_menu_structure()
            pages = structure.get("pages", [])
            all_links = set()

            # Collect all href values mentioned across page content (heuristic)
            wp = self._wp()
            for page in pages:
                try:
                    page_data = wp.get_post_by_url(page.get("link", ""))
                    if page_data:
                        content = page_data.get("content", {}).get("rendered", "")
                        soup = BeautifulSoup(content, "lxml")
                        for a_tag in soup.find_all("a", href=True):
                            all_links.add(a_tag["href"].rstrip("/"))
                except Exception:  # noqa: BLE001
                    pass

            orphans = [
                {"id": p["id"], "title": p["title"], "url": p["link"]}
                for p in pages
                if p.get("link", "").rstrip("/") not in all_links
            ]
            return orphans
        except Exception as exc:  # noqa: BLE001
            logger.warning("find_orphan_pages failed: %s", exc)
            return []

    def find_missing_pages(self, url: str) -> List[Dict[str, Any]]:
        """Check if a URL/page exists; if not, suggest creating it.

        Args:
            url: URL to check.

        Returns:
            List of suggestion dicts (empty list if page exists).
        """
        try:
            wp = self._wp()
            page = wp.get_post_by_url(url)
            if page:
                return []
            # Derive a suggested title from the URL
            slug = url.rstrip("/").split("/")[-1].replace("-", " ").replace("_", " ").title()
            return [
                {
                    "url": url,
                    "suggested_title": slug,
                    "suggested_slug": url.rstrip("/").split("/")[-1],
                    "reason": "Page not found — consider creating it",
                }
            ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("find_missing_pages failed for %s: %s", url, exc)
            return []

    def get_link_graph(self) -> Dict[str, Any]:
        """Return the internal link structure as a graph.

        Returns:
            Dict with nodes (list of {id, title, url}) and edges
            (list of {source_url, target_url}).
        """
        try:
            from bs4 import BeautifulSoup

            structure = self.get_menu_structure()
            pages = structure.get("pages", [])
            nodes = [
                {"id": p["id"], "title": p["title"], "url": p["link"]}
                for p in pages
            ]
            edges: List[Dict[str, str]] = []

            wp = self._wp()
            for page in pages:
                try:
                    page_data = wp.get_post_by_url(page.get("link", ""))
                    if page_data:
                        content = page_data.get("content", {}).get("rendered", "")
                        soup = BeautifulSoup(content, "lxml")
                        for a_tag in soup.find_all("a", href=True):
                            href = a_tag["href"]
                            if "studytips.in" in href or href.startswith("/"):
                                edges.append({
                                    "source_url": page["link"],
                                    "target_url": href,
                                })
                except Exception:  # noqa: BLE001
                    pass

            return {"nodes": nodes, "edges": edges}
        except Exception as exc:  # noqa: BLE001
            logger.warning("get_link_graph failed: %s", exc)
            return {"nodes": [], "edges": []}
