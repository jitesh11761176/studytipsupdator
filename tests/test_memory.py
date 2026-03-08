"""Tests for AgentMemory."""

from __future__ import annotations

import os
import tempfile

import pytest

from agent.core.memory import AgentMemory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_memory():
    """Return an AgentMemory backed by a temporary SQLite file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    memory = AgentMemory(db_path=db_path)
    yield memory

    try:
        os.unlink(db_path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLogInteraction:
    """Tests for AgentMemory.log_interaction."""

    def test_returns_positive_id(self, tmp_memory):
        action_id = tmp_memory.log_interaction(
            prompt="Write a blog post",
            intent="create_content",
            plan=["Step 1", "Step 2"],
            results={"status": "draft"},
        )
        assert action_id > 0

    def test_logs_are_retrievable(self, tmp_memory):
        tmp_memory.log_interaction(prompt="Test prompt", intent="general")
        recent = tmp_memory.get_recent_interactions(limit=1)
        assert len(recent) == 1
        assert recent[0]["prompt"] == "Test prompt"
        assert recent[0]["intent"] == "general"

    def test_multiple_logs_ordered_by_date(self, tmp_memory):
        tmp_memory.log_interaction(prompt="First", intent="create_content")
        tmp_memory.log_interaction(prompt="Second", intent="seo_optimize")

        recent = tmp_memory.get_recent_interactions(limit=2)
        assert len(recent) == 2
        # Most recent first
        assert recent[0]["prompt"] == "Second"


class TestRecordFeedback:
    """Tests for AgentMemory.record_feedback."""

    def test_approve_sets_approved_flag(self, tmp_memory):
        action_id = tmp_memory.log_interaction(prompt="Test", intent="general")
        tmp_memory.record_feedback(action_id=action_id, approved=True)

        recent = tmp_memory.get_recent_interactions(limit=1)
        assert recent[0]["approved"] == 1

    def test_reject_sets_approved_zero(self, tmp_memory):
        action_id = tmp_memory.log_interaction(prompt="Test", intent="general")
        tmp_memory.record_feedback(action_id=action_id, approved=False)

        recent = tmp_memory.get_recent_interactions(limit=1)
        assert recent[0]["approved"] == 0

    def test_feedback_with_text_adds_knowledge(self, tmp_memory):
        action_id = tmp_memory.log_interaction(prompt="Test", intent="general")
        tmp_memory.record_feedback(
            action_id=action_id, approved=False, feedback="Content was too long"
        )

        knowledge = tmp_memory.get_site_knowledge("user_feedback")
        assert len(knowledge) > 0
        assert "Content was too long" in knowledge[0]["fact"]


class TestStylePreferences:
    """Tests for style preference storage."""

    def test_set_and_get_style_preference(self, tmp_memory):
        tmp_memory.set_style_preference("tone", "informative")
        guide = tmp_memory.get_style_guide()
        assert guide["tone"] == "informative"

    def test_upsert_updates_existing_preference(self, tmp_memory):
        tmp_memory.set_style_preference("tone", "formal")
        tmp_memory.set_style_preference("tone", "casual")
        guide = tmp_memory.get_style_guide()
        assert guide["tone"] == "casual"

    def test_empty_style_guide_returns_empty_dict(self, tmp_memory):
        guide = tmp_memory.get_style_guide()
        assert isinstance(guide, dict)


class TestWinningStrategies:
    """Tests for winning strategy tracking."""

    def test_add_and_retrieve_winning_strategy(self, tmp_memory):
        tmp_memory.add_winning_strategy("content", "Use bullet points and numbered lists")
        strategies = tmp_memory.get_winning_strategies("content")
        assert len(strategies) == 1
        assert "bullet" in strategies[0]["description"]

    def test_repeated_strategy_increments_count(self, tmp_memory):
        desc = "Include FAQ section"
        tmp_memory.add_winning_strategy("content", desc)
        tmp_memory.add_winning_strategy("content", desc)
        strategies = tmp_memory.get_winning_strategies("content")
        assert strategies[0]["success_count"] == 2

    def test_different_types_do_not_mix(self, tmp_memory):
        tmp_memory.add_winning_strategy("content", "Use H2 headings")
        tmp_memory.add_winning_strategy("seo", "Target long-tail keywords")

        content_strategies = tmp_memory.get_winning_strategies("content")
        seo_strategies = tmp_memory.get_winning_strategies("seo")
        assert len(content_strategies) == 1
        assert len(seo_strategies) == 1


class TestContentPerformance:
    """Tests for content performance tracking."""

    def test_update_and_retrieve_metrics(self, tmp_memory):
        tmp_memory.update_content_performance(
            post_id="42",
            metrics={"url": "https://studytips.in/post", "views": 100, "position": 5.2},
        )

        with tmp_memory._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM content_performance WHERE post_id = ?", ("42",)
            ).fetchone()
        assert row is not None
        assert row["views"] == 100

    def test_update_existing_post_metrics(self, tmp_memory):
        tmp_memory.update_content_performance("10", {"views": 50})
        tmp_memory.update_content_performance("10", {"views": 200})

        with tmp_memory._get_connection() as conn:
            rows = conn.execute(
                "SELECT COUNT(*) as cnt FROM content_performance WHERE post_id = ?", ("10",)
            ).fetchone()
        assert rows["cnt"] == 1


class TestSiteKnowledge:
    """Tests for site knowledge base."""

    def test_add_and_retrieve_knowledge(self, tmp_memory):
        tmp_memory.add_site_knowledge(
            topic="site_info",
            fact="studytips.in focuses on Indian students",
            source="manual",
        )
        facts = tmp_memory.get_site_knowledge("site_info")
        assert len(facts) == 1
        assert "Indian students" in facts[0]["fact"]

    def test_different_topics_are_isolated(self, tmp_memory):
        tmp_memory.add_site_knowledge("topic_a", "Fact A", "src")
        tmp_memory.add_site_knowledge("topic_b", "Fact B", "src")

        a_facts = tmp_memory.get_site_knowledge("topic_a")
        b_facts = tmp_memory.get_site_knowledge("topic_b")
        assert len(a_facts) == 1
        assert len(b_facts) == 1
