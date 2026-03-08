"""Content generation and management engine for StudyTips AI Agent."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BLOG_POST_SYSTEM_PROMPT = (
    "You are an expert content writer for studytips.in, an Indian educational website "
    "covering study techniques, exam tips, learning strategies, and student success. "
    "Write in a helpful, authoritative tone with clear headings and actionable advice. "
    "Always create content as a DRAFT for human review before publishing."
)


class ContentEngine:
    """Generates and manages content for the WordPress site.

    Uses the brain router to select the best LLM for each content task.

    Args:
        brain_router: BrainRouter instance.
        config: AppConfig instance.
    """

    def __init__(self, brain_router: Any, config: Any) -> None:
        self.brain = brain_router
        self.config = config

    def generate_blog_post(
        self,
        topic: str,
        keywords: Optional[List[str]] = None,
        word_count: int = 1200,
        style: str = "informative",
        target_audience: str = "students",
    ) -> Dict[str, Any]:
        """Generate a full, SEO-optimised blog post as a draft.

        Args:
            topic: Blog post topic.
            keywords: Target keywords to incorporate.
            word_count: Approximate target word count.
            style: Writing style ('informative', 'listicle', 'how-to', 'guide').
            target_audience: Target reader (e.g. 'students', 'teachers').

        Returns:
            Dict with title, content, meta_description, slug, outline.
        """
        keywords = keywords or []
        keyword_str = ", ".join(keywords) if keywords else topic

        prompt = (
            f"Write a {style} blog post about: {topic}\n\n"
            f"Target keywords: {keyword_str}\n"
            f"Target audience: {target_audience}\n"
            f"Target word count: ~{word_count} words\n\n"
            "Requirements:\n"
            "- SEO-optimised H1 title\n"
            "- Engaging introduction\n"
            "- Well-structured body with H2/H3 subheadings\n"
            "- Practical, actionable advice\n"
            "- Strong conclusion with CTA\n"
            "- Return as JSON: {\"title\": ..., \"content\": ..., \"meta_description\": ..., \"slug\": ...}"
        )

        brain_name = self.brain.route("create_content", priority="quality")
        raw = self.brain.generate(
            brain_name=brain_name,
            prompt=prompt,
            system_prompt=BLOG_POST_SYSTEM_PROMPT,
        )

        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(raw[start:end])
            else:
                result = {"title": topic, "content": raw, "meta_description": "", "slug": ""}
        except json.JSONDecodeError:
            result = {"title": topic, "content": raw, "meta_description": "", "slug": ""}

        result["keywords"] = keywords
        result["word_count_target"] = word_count
        result["status"] = "draft"
        return result

    def update_content(
        self,
        url_or_id: str,
        instructions: str,
    ) -> Dict[str, Any]:
        """Fetch existing content and update it according to instructions.

        Args:
            url_or_id: URL slug or WordPress post ID.
            instructions: What to update (e.g. 'refresh statistics', 'add FAQ section').

        Returns:
            Dict with updated content and change summary.
        """
        from agent.integrations.wordpress_api import WordPressClient

        wp = WordPressClient(config=self.config.wp)

        try:
            if url_or_id.isdigit():
                post = wp.get_post(int(url_or_id))
            else:
                post = wp.get_post_by_url(url_or_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not fetch post %s: %s", url_or_id, exc)
            post = None

        existing_content = post.get("content", {}).get("rendered", "") if post else ""

        prompt = (
            f"Update the following blog post content according to these instructions:\n\n"
            f"Instructions: {instructions}\n\n"
            f"Existing content (excerpt):\n{existing_content[:2000]}\n\n"
            "Return the updated full content as HTML. Maintain the existing structure "
            "and improve upon it. Create as a DRAFT."
        )

        brain_name = self.brain.route("update_content", len(existing_content), priority="quality")
        updated_content = self.brain.generate(
            brain_name=brain_name,
            prompt=prompt,
            system_prompt=BLOG_POST_SYSTEM_PROMPT,
        )

        return {
            "post_id": post.get("id") if post else None,
            "original_url": url_or_id,
            "updated_content": updated_content,
            "instructions_applied": instructions,
            "status": "draft",
        }

    def generate_content_calendar(
        self,
        focus_topics: Optional[List[str]] = None,
        posts_per_week: int = 3,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Plan a content calendar for the specified period.

        Args:
            focus_topics: Optional list of topic areas to focus on.
            posts_per_week: Number of posts to plan per week.
            days: Planning horizon in days.

        Returns:
            Dict with calendar entries.
        """
        topics_str = (
            ", ".join(focus_topics)
            if focus_topics
            else "study tips, exam preparation, learning strategies, productivity, career guidance"
        )

        prompt = (
            f"Create a {days}-day content calendar for studytips.in with {posts_per_week} posts per week.\n\n"
            f"Focus topics: {topics_str}\n\n"
            "For each post provide:\n"
            "- date (YYYY-MM-DD)\n"
            "- title\n"
            "- primary_keyword\n"
            "- content_type (blog, guide, listicle, how-to)\n"
            "- brief_outline (2-3 sentences)\n\n"
            "Return as JSON array of post objects."
        )

        brain_name = self.brain.route("content_plan", priority="balanced")
        raw = self.brain.generate(
            brain_name=brain_name,
            prompt=prompt,
            system_prompt=BLOG_POST_SYSTEM_PROMPT,
        )

        try:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            calendar_entries = json.loads(raw[start:end]) if start >= 0 else []
        except json.JSONDecodeError:
            calendar_entries = []

        return {
            "period_days": days,
            "posts_per_week": posts_per_week,
            "focus_topics": focus_topics,
            "entries": calendar_entries,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def suggest_topics(self, count: int = 5) -> List[str]:
        """Suggest trending and relevant blog post topics.

        Args:
            count: Number of topics to suggest.

        Returns:
            List of topic strings.
        """
        prompt = (
            f"Suggest {count} trending and SEO-valuable blog post topics for studytips.in "
            "covering study tips, exam preparation, learning strategies, and student success in India. "
            "Return as a JSON array of topic strings."
        )

        brain_name = self.brain.route("content_plan", priority="speed")
        raw = self.brain.generate(brain_name=brain_name, prompt=prompt)

        try:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            return json.loads(raw[start:end]) if start >= 0 else []
        except json.JSONDecodeError:
            return []

    def find_stale_posts(self, older_than_days: int = 180) -> List[Dict[str, Any]]:
        """Find posts that haven't been updated recently.

        Args:
            older_than_days: Consider posts stale if not updated in this many days.

        Returns:
            List of stale post dicts.
        """
        from agent.integrations.wordpress_api import WordPressClient

        wp = WordPressClient(config=self.config.wp)
        posts = wp.get_posts(per_page=100)

        cutoff = datetime.utcnow() - timedelta(days=older_than_days)
        stale = []
        for post in posts:
            modified_str = post.get("modified", "")
            if modified_str:
                try:
                    modified = datetime.fromisoformat(modified_str.replace("Z", "+00:00"))
                    if modified.replace(tzinfo=None) < cutoff:
                        stale.append({
                            "id": post["id"],
                            "title": post.get("title", {}).get("rendered", ""),
                            "modified": modified_str,
                            "link": post.get("link", ""),
                        })
                except ValueError:
                    pass
        return stale

    def generate_outline(
        self, topic: str, keywords: Optional[List[str]] = None
    ) -> str:
        """Generate a structured blog post outline.

        Args:
            topic: Article topic.
            keywords: Target keywords.

        Returns:
            Markdown outline string.
        """
        keywords = keywords or []
        kw_str = ", ".join(keywords) if keywords else topic

        prompt = (
            f"Create a detailed blog post outline for: {topic}\n"
            f"Target keywords: {kw_str}\n\n"
            "Include: H1 title, introduction notes, H2 sections with H3 subsections, "
            "key points for each section, and conclusion notes. Format as Markdown."
        )

        brain_name = self.brain.route("create_content", priority="speed")
        return self.brain.generate(brain_name=brain_name, prompt=prompt)

    def check_plagiarism(self, content: str) -> Dict[str, Any]:
        """Perform a basic plagiarism check on content.

        Note: This is a lightweight check using LLM assessment, not a dedicated
        plagiarism detection service.

        Args:
            content: Content text to check.

        Returns:
            Dict with assessment and suggestions.
        """
        prompt = (
            "Review the following content and assess its originality. "
            "Identify any phrases that sound overly generic or copied. "
            "Provide a brief originality score (1-10) and suggestions for improvement.\n\n"
            f"Content:\n{content[:3000]}"
        )
        brain_name = self.brain.route("general", priority="speed")
        result = self.brain.generate(brain_name=brain_name, prompt=prompt)
        return {"assessment": result, "content_length": len(content)}
