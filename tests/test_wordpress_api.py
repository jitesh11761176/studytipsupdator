"""Tests for WordPress API client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def wp_config():
    """Return a minimal WP config mock."""
    config = MagicMock()
    config.site_url = "https://studytips.in"
    config.username = "testuser"
    config.app_password = "testpassword"
    config.api_base = "https://studytips.in/wp-json/wp/v2"
    return config


@pytest.fixture
def wp_client(wp_config):
    """Return a WordPressClient with mocked session."""
    from agent.integrations.wordpress_api import WordPressClient

    client = WordPressClient(config=wp_config)
    return client


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _mock_response(data: dict | list, status_code: int = 200):
    """Create a mock requests.Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = data
    mock.raise_for_status = MagicMock()
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWordPressClientPosts:
    """Tests for post-related WordPress API methods."""

    def test_create_post_returns_dict(self, wp_client):
        expected = {"id": 1, "title": {"rendered": "Test"}, "status": "draft"}
        with patch.object(wp_client._session, "request", return_value=_mock_response(expected)):
            result = wp_client.create_post(title="Test", content="<p>Hello</p>")
        assert result["id"] == 1
        assert result["status"] == "draft"

    def test_create_post_defaults_to_draft(self, wp_client):
        with patch.object(wp_client._session, "request", return_value=_mock_response({"id": 2, "status": "draft"})) as mock_req:
            wp_client.create_post(title="Draft Test", content="<p>Content</p>")
            call_kwargs = mock_req.call_args
            # Verify 'status' was 'draft' in the JSON payload
            json_payload = call_kwargs[1].get("json", {})
            assert json_payload.get("status") == "draft"

    def test_get_post(self, wp_client):
        expected = {"id": 42, "title": {"rendered": "My Post"}}
        with patch.object(wp_client._session, "request", return_value=_mock_response(expected)):
            result = wp_client.get_post(42)
        assert result["id"] == 42

    def test_update_post(self, wp_client):
        expected = {"id": 5, "title": {"rendered": "Updated"}}
        with patch.object(wp_client._session, "request", return_value=_mock_response(expected)):
            result = wp_client.update_post(5, title="Updated")
        assert result["id"] == 5

    def test_get_posts_returns_list(self, wp_client):
        expected = [{"id": 1}, {"id": 2}]
        with patch.object(wp_client._session, "request", return_value=_mock_response(expected)):
            result = wp_client.get_posts(per_page=10)
        assert len(result) == 2

    def test_get_post_by_url_found(self, wp_client):
        expected = [{"id": 10, "title": {"rendered": "Found"}}]
        with patch.object(wp_client._session, "request", return_value=_mock_response(expected)):
            result = wp_client.get_post_by_url("https://studytips.in/study-tips")
        assert result["id"] == 10

    def test_get_post_by_url_not_found(self, wp_client):
        with patch.object(wp_client._session, "request", return_value=_mock_response([])):
            result = wp_client.get_post_by_url("https://studytips.in/nonexistent")
        assert result is None


class TestWordPressClientPages:
    """Tests for page-related WordPress API methods."""

    def test_create_page_defaults_draft(self, wp_client):
        expected = {"id": 100, "status": "draft"}
        with patch.object(wp_client._session, "request", return_value=_mock_response(expected)) as mock_req:
            result = wp_client.create_page(title="New Page", content="<p>Page content</p>")
        assert result["status"] == "draft"

    def test_update_page(self, wp_client):
        expected = {"id": 100, "title": {"rendered": "Updated Page"}}
        with patch.object(wp_client._session, "request", return_value=_mock_response(expected)):
            result = wp_client.update_page(100, title="Updated Page")
        assert result["id"] == 100


class TestWordPressClientCategories:
    """Tests for category methods."""

    def test_get_or_create_category_existing(self, wp_client):
        existing = [{"id": 3, "name": "Study Tips"}]
        with patch.object(wp_client._session, "request", return_value=_mock_response(existing)):
            result = wp_client.get_or_create_category("Study Tips")
        assert result["id"] == 3

    def test_get_or_create_category_new(self, wp_client):
        # First call: search returns empty; second call: create returns new cat
        responses = [_mock_response([]), _mock_response({"id": 99, "name": "New Cat"})]
        with patch.object(wp_client._session, "request", side_effect=responses):
            result = wp_client.get_or_create_category("New Cat")
        assert result["id"] == 99

    def test_get_all_categories(self, wp_client):
        cats = [{"id": 1, "name": "Cat A"}, {"id": 2, "name": "Cat B"}]
        with patch.object(wp_client._session, "request", return_value=_mock_response(cats)):
            result = wp_client.get_all_categories()
        assert len(result) == 2


class TestWordPressClientSiteMap:
    """Tests for site map method."""

    def test_get_full_site_map_returns_totals(self, wp_client):
        with patch.object(wp_client._session, "request", return_value=_mock_response([])):
            result = wp_client.get_full_site_map()
        assert "totals" in result
        assert "pages" in result
        assert "categories" in result
