"""WordPress REST API client for StudyTips AI Agent.

Provides full CRUD operations for posts, pages, media, categories, tags,
and menus. All write operations default to status='draft' for safety.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30
_MAX_RETRIES = 3
_BACKOFF_FACTOR = 0.5


def _build_session(username: str, app_password: str) -> requests.Session:
    """Build a requests Session with basic auth and retry logic."""
    session = requests.Session()
    session.auth = (username, app_password)
    retry = Retry(
        total=_MAX_RETRIES,
        backoff_factor=_BACKOFF_FACTOR,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class WordPressClient:
    """Full-featured WordPress REST API v2 client.

    Args:
        config: WPConfig dataclass instance.
    """

    def __init__(self, config: Any) -> None:
        self.config = config
        self.api_base = config.api_base
        self._session = _build_session(config.username, config.app_password)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> Any:
        """Make an authenticated API request.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE).
            endpoint: API endpoint path (relative to api_base).
            **kwargs: Extra args forwarded to requests.

        Returns:
            Parsed JSON response.

        Raises:
            requests.HTTPError: On non-2xx responses after retries.
        """
        url = f"{self.api_base}/{endpoint.lstrip('/')}"
        kwargs.setdefault("timeout", _DEFAULT_TIMEOUT)
        response = self._session.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------
    # Posts
    # ------------------------------------------------------------------

    def create_post(
        self,
        title: str,
        content: str,
        status: str = "draft",
        slug: str = "",
        categories: Optional[List[int]] = None,
        tags: Optional[List[int]] = None,
        meta: Optional[Dict[str, Any]] = None,
        featured_media: Optional[int] = None,
        excerpt: str = "",
    ) -> Dict[str, Any]:
        """Create a new WordPress post.

        Args:
            title: Post title.
            content: Post HTML content.
            status: 'draft', 'publish', 'private', 'pending'.
            slug: URL slug (auto-generated from title if empty).
            categories: List of category IDs.
            tags: List of tag IDs.
            meta: Custom meta fields dict.
            featured_media: Featured image media ID.
            excerpt: Post excerpt.

        Returns:
            Created post object from WP REST API.
        """
        payload: Dict[str, Any] = {
            "title": title,
            "content": content,
            "status": status,
            "excerpt": excerpt,
        }
        if slug:
            payload["slug"] = slug
        if categories:
            payload["categories"] = categories
        if tags:
            payload["tags"] = tags
        if meta:
            payload["meta"] = meta
        if featured_media:
            payload["featured_media"] = featured_media

        return self._request("POST", "posts", json=payload)

    def update_post(self, post_id: int, **updates: Any) -> Dict[str, Any]:
        """Update an existing post by ID.

        Args:
            post_id: WordPress post ID.
            **updates: Fields to update.

        Returns:
            Updated post object.
        """
        return self._request("POST", f"posts/{post_id}", json=updates)

    def get_post(self, post_id: int) -> Dict[str, Any]:
        """Fetch a single post by ID.

        Args:
            post_id: WordPress post ID.

        Returns:
            Post object.
        """
        return self._request("GET", f"posts/{post_id}")

    def get_post_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetch a post or page by its URL slug.

        Args:
            url: Full URL or slug of the post/page.

        Returns:
            Post/page object or None if not found.
        """
        # Try slug extracted from URL
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        for post_type in ("posts", "pages"):
            try:
                results = self._request("GET", post_type, params={"slug": slug, "_embed": 1})
                if results:
                    return results[0]
            except Exception:  # noqa: BLE001
                continue
        return None

    def get_posts(
        self,
        per_page: int = 10,
        page: int = 1,
        search: str = "",
        categories: Optional[List[int]] = None,
        tags: Optional[List[int]] = None,
        status: str = "publish",
    ) -> List[Dict[str, Any]]:
        """Retrieve a list of posts with optional filters.

        Args:
            per_page: Number of posts per page.
            page: Page number.
            search: Search string.
            categories: Filter by category IDs.
            tags: Filter by tag IDs.
            status: Post status filter.

        Returns:
            List of post objects.
        """
        params: Dict[str, Any] = {
            "per_page": per_page,
            "page": page,
            "status": status,
        }
        if search:
            params["search"] = search
        if categories:
            params["categories"] = ",".join(str(c) for c in categories)
        if tags:
            params["tags"] = ",".join(str(t) for t in tags)
        return self._request("GET", "posts", params=params)

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    def create_page(
        self,
        title: str,
        content: str,
        parent: int = 0,
        template: str = "",
        status: str = "draft",
        slug: str = "",
        menu_order: int = 0,
    ) -> Dict[str, Any]:
        """Create a new WordPress page.

        Args:
            title: Page title.
            content: Page HTML content.
            parent: Parent page ID (0 = top-level).
            template: Page template filename.
            status: 'draft', 'publish', etc.
            slug: URL slug (auto-generated from title if empty).
            menu_order: Order in menu.

        Returns:
            Created page object.
        """
        payload: Dict[str, Any] = {
            "title": title,
            "content": content,
            "parent": parent,
            "status": status,
            "menu_order": menu_order,
        }
        if slug:
            payload["slug"] = slug
        if template:
            payload["template"] = template
        return self._request("POST", "pages", json=payload)

    def update_page(self, page_id: int, **updates: Any) -> Dict[str, Any]:
        """Update an existing page by ID.

        Args:
            page_id: WordPress page ID.
            **updates: Fields to update.

        Returns:
            Updated page object.
        """
        return self._request("POST", f"pages/{page_id}", json=updates)

    def get_pages(
        self,
        per_page: int = 100,
        page: int = 1,
        status: str = "publish",
        parent: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve a list of pages.

        Args:
            per_page: Max results per page.
            page: Page number.
            status: Page status filter.
            parent: Filter by parent page ID.

        Returns:
            List of page objects.
        """
        params: Dict[str, Any] = {"per_page": per_page, "page": page, "status": status}
        if parent is not None:
            params["parent"] = parent
        return self._request("GET", "pages", params=params)

    # ------------------------------------------------------------------
    # Categories & Tags
    # ------------------------------------------------------------------

    def get_all_categories(self) -> List[Dict[str, Any]]:
        """Return all categories (fetches all pages).

        Returns:
            List of category objects.
        """
        all_cats: List[Dict[str, Any]] = []
        page = 1
        while True:
            results = self._request(
                "GET", "categories", params={"per_page": 100, "page": page}
            )
            if not results:
                break
            all_cats.extend(results)
            if len(results) < 100:
                break
            page += 1
        return all_cats

    def get_or_create_category(
        self, name: str, parent: int = 0
    ) -> Dict[str, Any]:
        """Get an existing category or create it if it does not exist.

        Args:
            name: Category name.
            parent: Parent category ID.

        Returns:
            Category object.
        """
        categories = self._request("GET", "categories", params={"search": name})
        for cat in categories:
            if cat["name"].lower() == name.lower():
                return cat
        return self._request("POST", "categories", json={"name": name, "parent": parent})

    def get_all_tags(self) -> List[Dict[str, Any]]:
        """Return all tags.

        Returns:
            List of tag objects.
        """
        all_tags: List[Dict[str, Any]] = []
        page = 1
        while True:
            results = self._request(
                "GET", "tags", params={"per_page": 100, "page": page}
            )
            if not results:
                break
            all_tags.extend(results)
            if len(results) < 100:
                break
            page += 1
        return all_tags

    def get_or_create_tag(self, name: str) -> Dict[str, Any]:
        """Get an existing tag or create it if it does not exist.

        Args:
            name: Tag name.

        Returns:
            Tag object.
        """
        tags = self._request("GET", "tags", params={"search": name})
        for tag in tags:
            if tag["name"].lower() == name.lower():
                return tag
        return self._request("POST", "tags", json={"name": name})

    # ------------------------------------------------------------------
    # Media
    # ------------------------------------------------------------------

    def upload_media(
        self, file_path: str, alt_text: str = "", title: str = ""
    ) -> Dict[str, Any]:
        """Upload a media file to WordPress.

        Args:
            file_path: Local path to the file.
            alt_text: Image alt text.
            title: Media title.

        Returns:
            Created media object.
        """
        import mimetypes
        import os

        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or "application/octet-stream"
        filename = os.path.basename(file_path)

        with open(file_path, "rb") as fh:
            response = self._request(
                "POST",
                "media",
                files={"file": (filename, fh, mime_type)},
                data={"alt_text": alt_text, "title": title or filename},
            )
        return response

    def upload_media_bytes(
        self, data: bytes, filename: str, mime_type: str = "",
        alt_text: str = "", title: str = "",
    ) -> Dict[str, Any]:
        """Upload raw bytes as a media file to WordPress.

        Args:
            data: Raw file bytes.
            filename: Filename including extension.
            mime_type: MIME type (auto-detected from filename if empty).
            alt_text: Image alt text.
            title: Media title.

        Returns:
            Created media object with ``source_url``.
        """
        import mimetypes as _mt

        if not mime_type:
            mime_type, _ = _mt.guess_type(filename)
            mime_type = mime_type or "application/octet-stream"

        response = self._request(
            "POST",
            "media",
            files={"file": (filename, data, mime_type)},
            data={"alt_text": alt_text, "title": title or filename},
        )
        return response

    def update_media(
        self,
        media_id: int,
        alt_text: str = "",
        caption: str = "",
        description: str = "",
    ) -> Dict[str, Any]:
        """Update media metadata.

        Args:
            media_id: WordPress media ID.
            alt_text: New alt text.
            caption: New caption.
            description: New description.

        Returns:
            Updated media object.
        """
        payload: Dict[str, Any] = {}
        if alt_text:
            payload["alt_text"] = alt_text
        if caption:
            payload["caption"] = caption
        if description:
            payload["description"] = description
        return self._request("POST", f"media/{media_id}", json=payload)

    # ------------------------------------------------------------------
    # Menus (requires WP menu endpoint plugin or custom endpoint)
    # ------------------------------------------------------------------

    def add_to_menu(
        self,
        menu_id: int,
        page_id: int,
        parent_item: int = 0,
    ) -> Dict[str, Any]:
        """Add a page to a WordPress navigation menu.

        Note: Requires the WP REST API Menus plugin or equivalent.

        Args:
            menu_id: WordPress menu ID.
            page_id: Page ID to add.
            parent_item: Parent menu item ID (0 = top level).

        Returns:
            Created menu item object.
        """
        payload = {
            "menu_item_parent": parent_item,
            "object_id": page_id,
            "object": "page",
            "type": "post_type",
            "status": "publish",
        }
        return self._request("POST", f"menus/{menu_id}/items", json=payload)

    # ------------------------------------------------------------------
    # Site structure
    # ------------------------------------------------------------------

    def get_full_site_map(self) -> Dict[str, Any]:
        """Return a comprehensive map of the site's content structure.

        Returns:
            Dict with pages, categories, tags counts.
        """
        pages = self.get_pages(per_page=100)
        categories = self.get_all_categories()
        tags = self.get_all_tags()
        posts = self.get_posts(per_page=100)

        return {
            "pages": pages,
            "categories": categories,
            "tags": tags,
            "recent_posts": posts,
            "totals": {
                "pages": len(pages),
                "categories": len(categories),
                "tags": len(tags),
                "posts": len(posts),
            },
        }
