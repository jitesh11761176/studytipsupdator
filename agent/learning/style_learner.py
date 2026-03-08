"""Style learner: learns user writing preferences over time."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from agent.core.memory import AgentMemory

logger = logging.getLogger(__name__)


class StyleLearner:
    """Learn the user's preferred writing style from approved content.

    Analyses approved content to extract patterns like tone, word count,
    structural preferences, and vocabulary level.

    Args:
        memory: AgentMemory instance.
    """

    def __init__(self, memory: AgentMemory) -> None:
        self.memory = memory

    def learn_from_content(
        self, content: str, approved: bool
    ) -> None:
        """Update the style profile based on a content sample.

        Args:
            content: The content text to learn from.
            approved: Whether this content was approved (True) or rejected (False).
        """
        if not content.strip():
            return

        metrics = self._extract_style_metrics(content)

        if approved:
            # Update learned averages
            for key, value in metrics.items():
                current = self.memory.get_style_guide().get(key)
                if current:
                    try:
                        # Simple exponential moving average
                        avg = float(current) * 0.7 + float(value) * 0.3
                        self.memory.set_style_preference(key, str(round(avg, 2)))
                    except (ValueError, TypeError):
                        self.memory.set_style_preference(key, str(value))
                else:
                    self.memory.set_style_preference(key, str(value))
        else:
            logger.debug("Rejected content — not updating style metrics")

    def learn_from_feedback(self, feedback: str, approved: bool) -> None:
        """Extract style hints from user feedback text.

        Args:
            feedback: User's free-text feedback.
            approved: Whether the associated action was approved.
        """
        if not feedback:
            return

        feedback_lower = feedback.lower()

        # Extract tone preferences
        tone_hints = {
            "formal": "formal",
            "informal": "informal",
            "casual": "casual",
            "professional": "professional",
            "friendly": "friendly",
        }
        for keyword, tone in tone_hints.items():
            if keyword in feedback_lower:
                self.memory.set_style_preference("preferred_tone", tone)
                break

        # Extract length preferences
        if any(w in feedback_lower for w in ("shorter", "concise", "brief", "too long")):
            current_wc = float(self.memory.get_style_guide().get("avg_word_count", 1200))
            self.memory.set_style_preference("avg_word_count", str(max(500, int(current_wc * 0.85))))
        elif any(w in feedback_lower for w in ("longer", "detailed", "comprehensive", "too short")):
            current_wc = float(self.memory.get_style_guide().get("avg_word_count", 1200))
            self.memory.set_style_preference("avg_word_count", str(min(3000, int(current_wc * 1.15))))

    def get_style_profile(self) -> Dict[str, str]:
        """Return the current learned style profile.

        Returns:
            Dict with style preference keys and values.
        """
        defaults = {
            "avg_word_count": "1200",
            "preferred_tone": "informative",
            "structure": "h1_h2_h3",
            "bullet_points": "yes",
            "include_faq": "yes",
            "include_cta": "yes",
        }
        profile = defaults.copy()
        profile.update(self.memory.get_style_guide())
        return profile

    def apply_style(self, content: str) -> str:
        """Add a style note to content for the LLM to adapt it.

        In practice, the style guide is injected as system prompt context
        rather than post-processing the content.

        Args:
            content: Raw content text.

        Returns:
            Content with style application note prepended.
        """
        profile = self.get_style_profile()
        style_note = (
            f"[Style: tone={profile.get('preferred_tone')}, "
            f"word_count≈{profile.get('avg_word_count')}, "
            f"structure={profile.get('structure')}]"
        )
        return f"{style_note}\n\n{content}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_style_metrics(self, content: str) -> Dict[str, Any]:
        """Extract measurable style metrics from content.

        Args:
            content: Content text (may include HTML).

        Returns:
            Dict of metric name -> value.
        """
        # Strip HTML
        plain = re.sub(r'<[^>]+>', ' ', content)
        words = plain.split()
        word_count = len(words)

        # Check structural elements
        has_h2 = bool(re.search(r'<h2', content, re.IGNORECASE) or "##" in content)
        has_h3 = bool(re.search(r'<h3', content, re.IGNORECASE) or "###" in content)
        has_bullets = bool(re.search(r'<ul|<li', content, re.IGNORECASE) or re.search(r'^\s*[-*]', content, re.MULTILINE))
        has_faq = bool(re.search(r'faq|frequently asked', content, re.IGNORECASE))

        # Avg sentence length (approx reading level indicator)
        sentences = re.split(r'[.!?]+', plain)
        avg_sentence_len = (
            sum(len(s.split()) for s in sentences if s.strip()) / max(len([s for s in sentences if s.strip()]), 1)
        )

        return {
            "avg_word_count": word_count,
            "has_h2": "yes" if has_h2 else "no",
            "has_h3": "yes" if has_h3 else "no",
            "has_bullets": "yes" if has_bullets else "no",
            "has_faq": "yes" if has_faq else "no",
            "avg_sentence_len": round(avg_sentence_len, 1),
        }
