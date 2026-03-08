"""Feedback storage for self-learning agent improvement."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from agent.core.memory import AgentMemory

logger = logging.getLogger(__name__)


class FeedbackStore:
    """Store and analyse user feedback to improve agent behaviour.

    Args:
        memory: AgentMemory instance to use for persistence.
    """

    def __init__(self, memory: AgentMemory) -> None:
        self.memory = memory

    def store_feedback(
        self,
        action_id: int,
        feedback_type: str,
        feedback_text: str = "",
        rating: int = 0,
    ) -> None:
        """Store feedback for a specific agent action.

        Args:
            action_id: The action_log row id.
            feedback_type: Type of feedback ('approve', 'reject', 'edit', 'rate').
            feedback_text: Free-text feedback comment.
            rating: Numeric rating (1-5, 0 = not rated).
        """
        approved = feedback_type in ("approve",)
        self.memory.record_feedback(
            action_id=action_id,
            approved=approved,
            feedback=feedback_text,
        )

        if feedback_text:
            self.memory.add_site_knowledge(
                topic=f"feedback_{feedback_type}",
                fact=json.dumps({
                    "action_id": action_id,
                    "feedback_type": feedback_type,
                    "text": feedback_text,
                    "rating": rating,
                }),
                source=f"feedback:{action_id}",
            )

        if rating >= 4 and feedback_type == "approve":
            self.memory.add_winning_strategy(
                strategy_type="approved_action",
                description=f"High-rated action (id={action_id}, rating={rating}): {feedback_text[:100]}",
            )

    def get_feedback_summary(self, action_type: str) -> Dict[str, Any]:
        """Summarise feedback patterns for a given action type.

        Args:
            action_type: The intent/action type to summarise.

        Returns:
            Dict with approval rate, common issues, and patterns.
        """
        rows = self.memory.get_recent_interactions(limit=100)
        relevant = [r for r in rows if r.get("intent") == action_type]

        if not relevant:
            return {"action_type": action_type, "total": 0, "approval_rate": 0}

        approved = sum(1 for r in relevant if r.get("approved") == 1)
        rejected = sum(1 for r in relevant if r.get("approved") == 0)
        pending = len(relevant) - approved - rejected

        return {
            "action_type": action_type,
            "total": len(relevant),
            "approved": approved,
            "rejected": rejected,
            "pending": pending,
            "approval_rate": round(approved / len(relevant) * 100, 1) if relevant else 0,
        }

    def get_improvement_suggestions(self) -> List[str]:
        """Generate improvement suggestions based on feedback patterns.

        Returns:
            List of improvement suggestion strings.
        """
        recent = self.memory.get_recent_interactions(limit=50)
        feedback_facts = self.memory.get_site_knowledge("feedback_reject")

        if not feedback_facts:
            return ["No rejection feedback collected yet. Keep building the feedback database."]

        feedback_texts = [
            json.loads(f["fact"]).get("text", "")
            for f in feedback_facts
            if f.get("fact")
        ]

        suggestions = []
        if feedback_texts:
            suggestions.append(f"Address common rejection reasons: {'; '.join(feedback_texts[:3])}")

        rejected_count = sum(1 for r in recent if r.get("approved") == 0)
        if rejected_count > 5:
            suggestions.append(f"High rejection rate ({rejected_count} in last 50): review action planning")

        winning = self.memory.get_winning_strategies("approved_action")
        if winning:
            suggestions.append(f"Replicate winning approach: {winning[0]['description'][:100]}")

        return suggestions or ["Continue collecting feedback to identify improvement areas."]
