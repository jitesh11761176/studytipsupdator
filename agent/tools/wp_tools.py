"""WordPress action tools for agent function calling."""

from __future__ import annotations

from typing import Any, Dict


def _create_blog_post(
    title: str,
    content: str,
    categories: str = "",
    tags: str = "",
    status: str = "draft",
) -> Dict[str, Any]:
    """Execute blog post creation."""
    from agent.core.config import load_config
    from agent.integrations.wordpress_api import WordPressClient

    config = load_config()
    wp = WordPressClient(config=config.wp)

    cat_ids = []
    if categories:
        for cat_name in [c.strip() for c in categories.split(",")]:
            cat = wp.get_or_create_category(cat_name)
            cat_ids.append(cat["id"])

    tag_ids = []
    if tags:
        for tag_name in [t.strip() for t in tags.split(",")]:
            tag = wp.get_or_create_tag(tag_name)
            tag_ids.append(tag["id"])

    return wp.create_post(
        title=title,
        content=content,
        status=status,
        categories=cat_ids or None,
        tags=tag_ids or None,
    )


create_blog_post_tool: Dict[str, Any] = {
    "name": "create_blog_post",
    "description": "Create a new blog post on studytips.in WordPress site (defaults to draft)",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Post title"},
            "content": {"type": "string", "description": "Post HTML content"},
            "categories": {"type": "string", "description": "Comma-separated category names"},
            "tags": {"type": "string", "description": "Comma-separated tag names"},
            "status": {"type": "string", "enum": ["draft", "publish", "pending"], "default": "draft"},
        },
        "required": ["title", "content"],
    },
    "execute": _create_blog_post,
}


def _update_page(page_id: int, **updates: Any) -> Dict[str, Any]:
    """Execute page update."""
    from agent.core.config import load_config
    from agent.integrations.wordpress_api import WordPressClient

    config = load_config()
    wp = WordPressClient(config=config.wp)
    return wp.update_page(page_id, **updates)


update_page_tool: Dict[str, Any] = {
    "name": "update_page",
    "description": "Update an existing WordPress page by ID",
    "parameters": {
        "type": "object",
        "properties": {
            "page_id": {"type": "integer", "description": "WordPress page ID"},
            "title": {"type": "string", "description": "New page title"},
            "content": {"type": "string", "description": "New page HTML content"},
            "status": {"type": "string", "enum": ["draft", "publish", "pending"]},
        },
        "required": ["page_id"],
    },
    "execute": _update_page,
}


def _upload_media(file_path: str, alt_text: str = "", title: str = "") -> Dict[str, Any]:
    """Execute media upload."""
    from agent.core.config import load_config
    from agent.integrations.wordpress_api import WordPressClient

    config = load_config()
    wp = WordPressClient(config=config.wp)
    return wp.upload_media(file_path=file_path, alt_text=alt_text, title=title)


upload_media_tool: Dict[str, Any] = {
    "name": "upload_media",
    "description": "Upload an image or file to the WordPress media library",
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Local file path to upload"},
            "alt_text": {"type": "string", "description": "Image alt text for accessibility"},
            "title": {"type": "string", "description": "Media title"},
        },
        "required": ["file_path"],
    },
    "execute": _upload_media,
}
