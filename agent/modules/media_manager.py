"""Media management module for StudyTips AI Agent."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MediaManager:
    """WordPress media upload and optimisation.

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

    def upload_image(
        self,
        file_path: str,
        alt_text: str = "",
        title: str = "",
    ) -> Dict[str, Any]:
        """Upload an image to WordPress media library.

        Args:
            file_path: Local path to image file.
            alt_text: Accessibility alt text.
            title: Media title.

        Returns:
            WordPress media object.
        """
        if not alt_text:
            alt_text = self.generate_alt_text(file_path)
        return self._wp().upload_media(
            file_path=file_path, alt_text=alt_text, title=title
        )

    def generate_alt_text(self, image_url_or_path: str) -> str:
        """Generate descriptive alt text for an image using AI.

        Args:
            image_url_or_path: URL or local path of the image.

        Returns:
            Generated alt text string.
        """
        # Extract filename for context
        filename = image_url_or_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        name_hint = filename.rsplit(".", 1)[0].replace("-", " ").replace("_", " ")

        prompt = (
            f"Generate a concise, descriptive alt text for an image on an educational website (studytips.in). "
            f"The image filename is: '{name_hint}'. "
            "Alt text should be descriptive, include relevant keywords, and be under 125 characters. "
            "Return only the alt text string."
        )
        brain_name = self.brain.route("general", priority="speed")
        return self.brain.generate(brain_name=brain_name, prompt=prompt).strip().strip('"')

    def optimize_images(self, post_id: int) -> List[Dict[str, Any]]:
        """Identify images in a post that lack proper optimisation.

        Args:
            post_id: WordPress post ID.

        Returns:
            List of image optimisation suggestions.
        """
        try:
            wp = self._wp()
            post = wp.get_post(post_id)
            content = post.get("content", {}).get("rendered", "")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not fetch post %d: %s", post_id, exc)
            return []

        import re
        img_tags = re.findall(r'<img[^>]+>', content)
        suggestions = []
        for img in img_tags:
            has_alt = 'alt="' in img or "alt='" in img
            has_lazy = "loading=" in img
            src_match = re.search(r'src=["\']([^"\']+)["\']', img)
            src = src_match.group(1) if src_match else ""
            suggestion: Dict[str, Any] = {"src": src}
            if not has_alt:
                suggestion["missing_alt"] = True
                suggestion["suggested_alt"] = self.generate_alt_text(src)
            if not has_lazy:
                suggestion["missing_lazy_load"] = True
            if suggestion:
                suggestions.append(suggestion)

        return suggestions

    def find_missing_alt_texts(self) -> List[Dict[str, Any]]:
        """Find all media items in the library that have no alt text.

        Returns:
            List of media objects with empty alt text.
        """
        try:
            from agent.integrations.wordpress_api import WordPressClient
            wp = WordPressClient(config=self.config.wp)
            media_list = wp._request("GET", "media", params={"per_page": 100, "media_type": "image"})
            return [
                {"id": m.get("id"), "url": m.get("source_url", ""), "title": m.get("title", {}).get("rendered", "")}
                for m in media_list
                if not m.get("alt_text", "").strip()
            ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not fetch media: %s", exc)
            return []
