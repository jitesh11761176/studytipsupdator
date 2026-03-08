"""Tests for Content Engine."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_brain_router():
    """Return a mock BrainRouter that returns predictable JSON responses."""
    router = MagicMock()
    router.route.return_value = "copilot"
    return router


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.wp.site_url = "https://studytips.in"
    config.wp.username = "test"
    config.wp.app_password = "test"
    config.wp.api_base = "https://studytips.in/wp-json/wp/v2"
    return config


@pytest.fixture
def content_engine(mock_brain_router, mock_config):
    from agent.modules.content_engine import ContentEngine
    return ContentEngine(brain_router=mock_brain_router, config=mock_config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGenerateBlogPost:
    """Tests for ContentEngine.generate_blog_post."""

    def test_returns_dict_with_title_and_content(self, content_engine, mock_brain_router):
        response_json = json.dumps({
            "title": "10 Best Study Tips",
            "content": "<h1>Study Tips</h1><p>Content here</p>",
            "meta_description": "Learn the top study tips.",
            "slug": "best-study-tips",
        })
        mock_brain_router.generate.return_value = response_json

        result = content_engine.generate_blog_post(topic="Study Tips", keywords=["study tips"])
        assert result["title"] == "10 Best Study Tips"
        assert result["status"] == "draft"

    def test_falls_back_on_non_json_response(self, content_engine, mock_brain_router):
        mock_brain_router.generate.return_value = "Plain text content without JSON"

        result = content_engine.generate_blog_post(topic="Exam Prep")
        assert "title" in result
        assert result["status"] == "draft"

    def test_includes_keywords_in_result(self, content_engine, mock_brain_router):
        mock_brain_router.generate.return_value = json.dumps({
            "title": "Test",
            "content": "Content",
            "meta_description": "Desc",
            "slug": "test",
        })
        keywords = ["exam tips", "study guide"]
        result = content_engine.generate_blog_post(topic="Exams", keywords=keywords)
        assert result["keywords"] == keywords


class TestGenerateOutline:
    """Tests for ContentEngine.generate_outline."""

    def test_returns_string(self, content_engine, mock_brain_router):
        mock_brain_router.generate.return_value = "# Outline\n## Section 1\n## Section 2"
        result = content_engine.generate_outline(topic="Time Management")
        assert isinstance(result, str)
        assert len(result) > 0


class TestSuggestTopics:
    """Tests for ContentEngine.suggest_topics."""

    def test_returns_list_of_topics(self, content_engine, mock_brain_router):
        mock_brain_router.generate.return_value = json.dumps([
            "How to study effectively",
            "NEET preparation tips",
            "Time management for students",
        ])
        topics = content_engine.suggest_topics(count=3)
        assert isinstance(topics, list)
        assert len(topics) == 3

    def test_handles_non_json_response(self, content_engine, mock_brain_router):
        mock_brain_router.generate.return_value = "Not a JSON array"
        topics = content_engine.suggest_topics(count=5)
        assert isinstance(topics, list)


class TestGenerateContentCalendar:
    """Tests for ContentEngine.generate_content_calendar."""

    def test_returns_calendar_structure(self, content_engine, mock_brain_router):
        entries = [
            {"date": "2026-01-01", "title": "Post 1", "primary_keyword": "study"},
            {"date": "2026-01-03", "title": "Post 2", "primary_keyword": "exam"},
        ]
        mock_brain_router.generate.return_value = json.dumps(entries)

        result = content_engine.generate_content_calendar(days=30, posts_per_week=3)
        assert result["period_days"] == 30
        assert result["posts_per_week"] == 3
        assert "entries" in result
        assert "generated_at" in result


class TestFindStalePosts:
    """Tests for ContentEngine.find_stale_posts."""

    def test_returns_list(self, content_engine, mock_config):
        mock_wp = MagicMock()
        mock_wp.get_posts.return_value = [
            {
                "id": 1,
                "title": {"rendered": "Old Post"},
                "modified": "2024-01-01T00:00:00",
                "link": "https://studytips.in/old-post",
            },
            {
                "id": 2,
                "title": {"rendered": "Recent Post"},
                "modified": "2026-02-01T00:00:00",
                "link": "https://studytips.in/recent-post",
            },
        ]

        with patch("agent.integrations.wordpress_api.WordPressClient", return_value=mock_wp):
            stale = content_engine.find_stale_posts(older_than_days=180)

        assert isinstance(stale, list)
        # The 2024 post should be stale
        stale_ids = [p["id"] for p in stale]
        assert 1 in stale_ids
