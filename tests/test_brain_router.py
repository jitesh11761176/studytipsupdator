"""Tests for Brain Router."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent.core.brain_router import BRAINS, TASK_ROUTING, BrainRouter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def router():
    """Return a BrainRouter with no config (keys not needed for routing tests)."""
    return BrainRouter(config=None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBrainDefinitions:
    """Tests for BRAINS registry configuration."""

    def test_all_brains_have_required_fields(self):
        for name, brain in BRAINS.items():
            assert brain.name == name
            assert brain.provider
            assert brain.model
            assert brain.best_for
            assert brain.cost_tier in ("free", "low", "medium", "high")
            assert 1 <= brain.speed_rating <= 5

    def test_task_routing_covers_common_intents(self):
        expected_intents = [
            "create_content",
            "update_content",
            "seo_optimize",
            "site_audit",
            "content_plan",
            "analytics",
            "general",
        ]
        for intent in expected_intents:
            assert intent in TASK_ROUTING, f"Intent '{intent}' missing from TASK_ROUTING"

    def test_task_routing_references_valid_brains(self):
        for task, candidates in TASK_ROUTING.items():
            for brain_name in candidates:
                assert brain_name in BRAINS, f"Unknown brain '{brain_name}' in route for '{task}'"


class TestBrainRouterRoute:
    """Tests for the route() method."""

    def test_route_returns_valid_brain(self, router):
        brain_name = router.route("create_content")
        assert brain_name in BRAINS

    def test_route_general_intent(self, router):
        brain_name = router.route("general")
        assert brain_name in BRAINS

    def test_route_unknown_intent_falls_back_to_general(self, router):
        brain_name = router.route("unknown_intent_xyz")
        assert brain_name in BRAINS

    def test_route_priority_cost_prefers_free(self, router):
        brain_name = router.route("general", priority="cost")
        brain = BRAINS[brain_name]
        # Should prefer 'free' tier when available
        assert brain.cost_tier in ("free", "low")

    def test_route_priority_speed_returns_fast_brain(self, router):
        brain_name = router.route("general", priority="speed")
        brain = BRAINS[brain_name]
        assert brain.speed_rating >= 2

    def test_route_filters_by_context_window(self, router):
        # A very large context should still return a valid brain
        brain_name = router.route("content_plan", content_length=100000)
        assert brain_name in BRAINS
        assert BRAINS[brain_name].context_window >= 100000

    def test_mark_unavailable_excludes_brain(self, router):
        router.mark_unavailable("local_ollama")
        # Ensure we can still route without it
        brain_name = router.route("general")
        assert brain_name != "local_ollama" or len(router._available_brains) == 1

    def test_mark_available_re_adds_brain(self, router):
        router.mark_unavailable("local_ollama")
        router.mark_available("local_ollama")
        assert "local_ollama" in router._available_brains


class TestBrainRouterGenerate:
    """Tests for the generate() method with mocked clients."""

    def test_generate_calls_client_and_returns_text(self, router):
        mock_client = MagicMock()
        mock_client.chat_completion.return_value = "Generated text"
        router._clients["local_ollama"] = mock_client

        result = router.generate(
            brain_name="local_ollama",
            prompt="Write something",
        )
        assert result == "Generated text"

    def test_generate_falls_back_on_failure(self, router):
        """If the primary brain fails, should try the next available brain."""
        failing_client = MagicMock()
        failing_client.chat_completion.side_effect = RuntimeError("API down")
        router._clients["copilot"] = failing_client

        success_client = MagicMock()
        success_client.chat_completion.return_value = "Fallback text"
        # Inject fallback client for every other brain
        for brain_name in BRAINS:
            if brain_name != "copilot":
                router._clients[brain_name] = success_client

        result = router.generate(brain_name="copilot", prompt="Test")
        assert result == "Fallback text"

    def test_generate_raises_when_all_fail(self, router):
        for brain_name in BRAINS:
            mock_client = MagicMock()
            mock_client.chat_completion.side_effect = RuntimeError("All down")
            router._clients[brain_name] = mock_client

        with pytest.raises(RuntimeError, match="All brains failed"):
            router.generate(brain_name="copilot", prompt="Test")
