"""Tests for SEO Optimizer."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_brain_router():
    router = MagicMock()
    router.route.return_value = "copilot"
    return router


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.wp.site_url = "https://studytips.in"
    config.wp.api_base = "https://studytips.in/wp-json/wp/v2"
    config.wp.username = "test"
    config.wp.app_password = "test"
    config.google.search_console_site = "https://studytips.in"
    config.google.service_account_key = ""
    return config


@pytest.fixture
def seo_optimizer(mock_brain_router, mock_config):
    from agent.modules.seo_optimizer import SEOOptimizer
    return SEOOptimizer(brain_router=mock_brain_router, config=mock_config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGenerateMeta:
    """Tests for SEOOptimizer.generate_meta."""

    def test_returns_dict_with_meta_fields(self, seo_optimizer, mock_brain_router):
        meta_response = json.dumps({
            "meta_title": "Study Tips for Students | StudyTips.in",
            "meta_description": "Discover the best study tips for Indian students. Improve your grades now!",
            "slug": "study-tips-for-students",
            "focus_keyword": "study tips",
            "secondary_keywords": ["exam tips", "learning strategies"],
        })
        mock_brain_router.generate.return_value = meta_response

        result = seo_optimizer.generate_meta(
            title="Study Tips",
            content="<p>Study tips content here...</p>",
        )
        assert "meta_title" in result
        assert "meta_description" in result
        assert "slug" in result

    def test_fallback_on_non_json_response(self, seo_optimizer, mock_brain_router):
        mock_brain_router.generate.return_value = "Not valid JSON"

        result = seo_optimizer.generate_meta(title="A" * 70, content="Content")
        assert "meta_title" in result
        assert len(result["meta_title"]) <= 60


class TestKeywordResearch:
    """Tests for SEOOptimizer.keyword_research."""

    def test_returns_keyword_dict(self, seo_optimizer, mock_brain_router):
        kw_response = json.dumps({
            "primary_keyword": "study tips for class 10",
            "secondary_keywords": ["exam tips", "board exam preparation"],
            "long_tail_keywords": ["how to study for class 10 board exams"],
            "search_intent": "informational",
            "difficulty": "medium",
            "monthly_search_volume": "1000-5000",
        })
        mock_brain_router.generate.return_value = kw_response

        result = seo_optimizer.keyword_research("study tips class 10")
        assert result["primary_keyword"] == "study tips for class 10"
        assert "secondary_keywords" in result
        assert "long_tail_keywords" in result

    def test_fallback_returns_topic_as_primary(self, seo_optimizer, mock_brain_router):
        mock_brain_router.generate.return_value = "Not JSON"

        result = seo_optimizer.keyword_research("exam tips")
        assert result["primary_keyword"] == "exam tips"


class TestFindInternalLinks:
    """Tests for SEOOptimizer.find_internal_links."""

    def test_returns_list(self, seo_optimizer, mock_brain_router):
        links_response = json.dumps([
            {"anchor_text": "time management tips", "target_url": "https://studytips.in/time-management", "context_sentence": "..."},
        ])
        mock_brain_router.generate.return_value = links_response

        result = seo_optimizer.find_internal_links(
            content="Learn about time management tips for students.",
            existing_posts=[{"id": 1, "title": {"rendered": "Time Management"}, "link": "https://studytips.in/time-management"}],
        )
        assert isinstance(result, list)

    def test_handles_empty_posts(self, seo_optimizer, mock_brain_router):
        mock_brain_router.generate.return_value = "[]"
        result = seo_optimizer.find_internal_links(content="Some content", existing_posts=[])
        assert result == []


class TestGenerateSchema:
    """Tests for SEOOptimizer.generate_schema."""

    def test_returns_non_empty_string(self, seo_optimizer, mock_brain_router):
        mock_brain_router.generate.return_value = (
            '<script type="application/ld+json">{"@type": "Article"}</script>'
        )
        result = seo_optimizer.generate_schema("article", "Some content")
        assert isinstance(result, str)
        assert len(result) > 0


class TestOptimizePost:
    """Tests for SEOOptimizer.optimize_post."""

    def test_optimize_post_returns_dict(self, seo_optimizer, mock_brain_router, mock_config):
        mock_wp = MagicMock()
        mock_wp.get_post.return_value = {
            "id": 42,
            "title": {"rendered": "Study Tips"},
            "content": {"rendered": "<p>Content</p>"},
        }
        mock_wp.get_posts.return_value = []

        mock_brain_router.generate.return_value = json.dumps({
            "meta_title": "Study Tips",
            "meta_description": "Best study tips",
            "slug": "study-tips",
        })

        with patch("agent.integrations.wordpress_api.WordPressClient", return_value=mock_wp):
            result = seo_optimizer.optimize_post("42")

        assert result["post_id"] == 42
        assert "meta" in result
        assert result["status"] == "draft"
