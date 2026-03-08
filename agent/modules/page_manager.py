"""Page management module for StudyTips AI Agent."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PageManager:
    """WordPress page CRUD with hierarchy management.

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

    def create_page(
        self,
        title: str,
        content: str,
        parent_page: int = 0,
        template: str = "",
        status: str = "draft",
    ) -> Dict[str, Any]:
        """Create a new WordPress page.

        Args:
            title: Page title.
            content: Page HTML content.
            parent_page: Parent page ID (0 = top level).
            template: Page template filename.
            status: 'draft' or 'publish'.

        Returns:
            Created page object.
        """
        return self._wp().create_page(
            title=title,
            content=content,
            parent=parent_page,
            template=template,
            status=status,
        )

    def update_page_by_url(
        self, url: str, instructions: str
    ) -> Dict[str, Any]:
        """Fetch a page by URL and update its content according to instructions.

        Args:
            url: Page URL or slug.
            instructions: Natural language update instructions.

        Returns:
            Dict with updated content (status='draft').
        """
        wp = self._wp()
        page = wp.get_post_by_url(url)

        if not page:
            return {"error": f"Page not found: {url}"}

        existing_content = page.get("content", {}).get("rendered", "")
        title = page.get("title", {}).get("rendered", "")

        prompt = (
            f"Update this WordPress page content based on the following instructions.\n\n"
            f"Page title: {title}\n"
            f"Instructions: {instructions}\n\n"
            f"Current content (excerpt):\n{existing_content[:3000]}\n\n"
            "Return the complete updated HTML content."
        )

        brain_name = self.brain.route("update_content", len(existing_content))
        updated = self.brain.generate(brain_name=brain_name, prompt=prompt)

        return {
            "page_id": page["id"],
            "title": title,
            "updated_content": updated,
            "instructions_applied": instructions,
            "status": "draft",
        }

    def organize_page_hierarchy(
        self, pages: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Suggest an improved page hierarchy for the site.

        Args:
            pages: List of page objects. Fetches from WP if omitted.

        Returns:
            Dict with current structure and suggested improvements.
        """
        if pages is None:
            pages = self._wp().get_pages(per_page=100)

        page_list = [
            {"id": p.get("id"), "title": p.get("title", {}).get("rendered", ""), "parent": p.get("parent", 0)}
            for p in pages
        ]

        import json
        prompt = (
            "Analyse this WordPress page hierarchy for studytips.in and suggest improvements.\n\n"
            f"Current pages:\n{json.dumps(page_list, indent=2)}\n\n"
            "Suggest a better parent-child structure for clarity and SEO. "
            "Return JSON with: current_issues (list) and suggested_hierarchy (list of {id, title, suggested_parent})."
        )

        brain_name = self.brain.route("site_audit", priority="balanced")
        raw = self.brain.generate(brain_name=brain_name, prompt=prompt)

        try:
            import json as _json
            start = raw.find("{")
            end = raw.rfind("}") + 1
            return _json.loads(raw[start:end]) if start >= 0 else {"raw": raw}
        except Exception:  # noqa: BLE001
            return {"raw": raw}

    def bulk_update(
        self,
        instructions: str,
        filter_criteria: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Update multiple pages matching filter criteria.

        Args:
            instructions: What to update on each page.
            filter_criteria: WP API query params to filter pages.

        Returns:
            List of update result dicts.
        """
        wp = self._wp()
        params = filter_criteria or {}
        pages = wp.get_pages(per_page=params.pop("per_page", 20))

        results = []
        for page in pages:
            result = self.update_page_by_url(
                url=page.get("link", ""),
                instructions=instructions,
            )
            results.append(result)

        return results

    def get_site_structure(self) -> Dict[str, Any]:
        """Return the current page hierarchy as a tree.

        Returns:
            Dict with nested page structure.
        """
        pages = self._wp().get_pages(per_page=100)

        # Build tree
        tree: Dict[int, Any] = {}
        for page in pages:
            tree[page["id"]] = {
                "id": page["id"],
                "title": page.get("title", {}).get("rendered", ""),
                "parent": page.get("parent", 0),
                "link": page.get("link", ""),
                "children": [],
            }

        roots = []
        for node in tree.values():
            parent_id = node["parent"]
            if parent_id and parent_id in tree:
                tree[parent_id]["children"].append(node)
            else:
                roots.append(node)

        return {"structure": roots, "total_pages": len(pages)}

    def get_page_content(self, url: str) -> Dict[str, Any]:
        """Fetch and return current page content by URL.

        Args:
            url: Page URL or slug.

        Returns:
            Dict with page id, title, content (rendered HTML), status, and link.
        """
        wp = self._wp()
        page = wp.get_post_by_url(url)
        if not page:
            return {"error": f"Page not found: {url}"}
        return {
            "page_id": page.get("id"),
            "title": page.get("title", {}).get("rendered", ""),
            "content": page.get("content", {}).get("rendered", ""),
            "status": page.get("status", ""),
            "link": page.get("link", ""),
        }

    def compare_versions(self, url: str, new_content: str) -> Dict[str, Any]:
        """Show a diff between current page content and proposed new content.

        Args:
            url: Page URL to fetch.
            new_content: Proposed replacement content.

        Returns:
            Dict with original, updated, and unified diff string.
        """
        current = self.get_page_content(url)
        if "error" in current:
            return current

        original = current.get("content", "")
        try:
            import diff_match_patch as dmp_module  # type: ignore[import-untyped]

            dmp = dmp_module.diff_match_patch()
            diffs = dmp.diff_main(original, new_content)
            dmp.diff_cleanupSemantic(diffs)
            diff_html = dmp.diff_prettyHtml(diffs)
        except Exception:  # noqa: BLE001
            import difflib

            diff_lines = difflib.unified_diff(
                original.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile="current",
                tofile="updated",
            )
            diff_html = "".join(diff_lines)

        return {
            "page_id": current.get("page_id"),
            "title": current.get("title", ""),
            "original": original,
            "updated": new_content,
            "diff_html": diff_html,
        }
