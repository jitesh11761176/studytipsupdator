"""Content generation and management engine for StudyTips AI Agent."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BLOG_POST_SYSTEM_PROMPT = (
    "You are an expert content writer for studytips.in, an Indian educational website "
    "covering study techniques, exam tips, learning strategies, and student success. "
    "Write in a helpful, authoritative tone with clear headings and actionable advice. "
    "Always create content as a DRAFT for human review before publishing."
)

PIPELINE_PLAN_PROMPT = (
    "You are a senior content strategist for studytips.in. "
    "Create a concise but high-impact plan for the requested article/page. "
    "Return ONLY valid JSON with keys: title, slug, focus_keyword, secondary_keywords, "
    "search_intent, audience, outline (array of H2 objects with optional h3 array), "
    "faq_questions (array), and internal_link_topics (array)."
)

PIPELINE_CRITIC_PROMPT = (
    "You are a strict editorial reviewer. Score this draft and return ONLY valid JSON with keys: "
    "seo_score (0-100), readability_score (0-100), depth_score (0-100), uniqueness_score (0-100), "
    "factual_confidence (0-100), weak_sections (array of strings), and rewrite_instructions (array of strings)."
)

PIPELINE_REWRITE_PROMPT = (
    "You are a principal editor. Rewrite and improve the draft according to critique feedback. "
    "Preserve strengths, fix weak sections, and return clean WordPress-compatible HTML only."
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

    # ------------------------------------------------------------------
    # Powerful multi-pass generation pipeline
    # ------------------------------------------------------------------

    def _clean_code_fences(self, text: str) -> str:
        cleaned = re.sub(r"^```(?:html|json|markdown)?\s*\n?", "", text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned.strip())
        return cleaned

    def _extract_json_object(self, raw: str, default: Dict[str, Any]) -> Dict[str, Any]:
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(raw[start:end])
                if isinstance(parsed, dict):
                    return parsed
        except Exception:  # noqa: BLE001
            pass
        return default

    def _safe_slug(self, value: str) -> str:
        value = value.lower().strip()
        value = re.sub(r"[^a-z0-9\s-]", "", value)
        value = re.sub(r"\s+", "-", value)
        value = re.sub(r"-+", "-", value)
        return value.strip("-")

    def _get_style_context(self) -> Dict[str, str]:
        defaults = {
            "avg_word_count": "1400",
            "preferred_tone": "authoritative but student-friendly",
            "has_h2": "yes",
            "has_h3": "yes",
            "has_bullets": "yes",
            "has_faq": "yes",
            "include_cta": "yes",
        }
        try:
            style = self.config and getattr(self, "config", None)
            if style is None:
                return defaults
            from agent.core.memory import AgentMemory

            memory = AgentMemory(db_path=self.config.agent.memory_db_path)
            learned = memory.get_style_guide()
            merged = defaults.copy()
            merged.update({k: str(v) for k, v in learned.items()})
            return merged
        except Exception:  # noqa: BLE001
            return defaults

    def _get_related_site_context(self, topic: str, keywords: List[str], limit: int = 6) -> List[Dict[str, str]]:
        context: List[Dict[str, str]] = []
        try:
            wp_cfg = getattr(self.config, "wp", None)
            username = (getattr(wp_cfg, "username", "") or "").strip().lower()
            app_password = (getattr(wp_cfg, "app_password", "") or "").strip().lower()
            # Skip network calls when credentials are not configured (or test mocks are in use).
            if not username or not app_password or username == "test" or app_password == "test":
                return context

            from agent.integrations.wordpress_api import WordPressClient

            wp = WordPressClient(config=self.config.wp)
            queries = [topic] + keywords[:3]
            seen_ids = set()
            for q in queries:
                try:
                    posts = wp.get_posts(per_page=10, page=1, search=q, status="publish")
                except Exception:  # noqa: BLE001
                    posts = []
                for post in posts:
                    pid = post.get("id")
                    if not pid or pid in seen_ids:
                        continue
                    seen_ids.add(pid)
                    context.append(
                        {
                            "title": post.get("title", {}).get("rendered", ""),
                            "slug": post.get("slug", ""),
                            "link": post.get("link", ""),
                            "excerpt": post.get("excerpt", {}).get("rendered", "")[:300],
                        }
                    )
                    if len(context) >= limit:
                        return context
        except Exception:  # noqa: BLE001
            return context
        return context

    def _passes_quality_gate(self, report: Dict[str, Any]) -> bool:
        gates = {
            "seo_score": 70,
            "readability_score": 65,
            "depth_score": 70,
            "uniqueness_score": 65,
            "factual_confidence": 65,
        }
        for key, min_score in gates.items():
            value = int(report.get(key, 0) or 0)
            if value < min_score:
                return False
        return True

    def _build_publish_assets(
        self,
        topic: str,
        title: str,
        slug: str,
        keyword: str,
        content_html: str,
        related_context: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        prompt = (
            "Generate publish-ready SEO assets from this content. Return ONLY valid JSON with keys: "
            "meta_description (max 160 chars), tags (array up to 8), faq (array of {question, answer}), "
            "internal_links (array of {anchor_text, target_slug, rationale}), "
            "schema_faq_jsonld (stringified JSON-LD).\n\n"
            f"Topic: {topic}\nTitle: {title}\nSlug: {slug}\nPrimary keyword: {keyword}\n\n"
            f"Existing related pages context:\n{json.dumps(related_context)[:2500]}\n\n"
            f"Content:\n{content_html[:7000]}"
        )
        brain_name = self.brain.route("seo_optimize", priority="quality")
        raw = self.brain.generate(brain_name=brain_name, prompt=prompt)
        default = {
            "meta_description": "",
            "tags": [],
            "faq": [],
            "internal_links": [],
            "schema_faq_jsonld": "",
        }
        return self._extract_json_object(raw, default)

    def generate_power_content(
        self,
        user_request: str,
        target_type: str = "post",
        keywords: Optional[List[str]] = None,
        word_count: int = 1400,
        style: str = "informative",
        target_audience: str = "students",
    ) -> Dict[str, Any]:
        """Generate high-quality content using a planner/writer/critic/rewrite pipeline.

        Args:
            user_request: User's full generation request.
            target_type: "post" or "page".
            keywords: Optional target keywords.
            word_count: Target article length.
            style: Preferred writing style.
            target_audience: Audience profile.

        Returns:
            Dict with final content and quality metadata.
        """
        keywords = keywords or []
        primary_keyword = keywords[0] if keywords else user_request
        style_context = self._get_style_context()
        related_context = self._get_related_site_context(user_request, keywords)

        # 1) Plan using speed-focused model
        plan_prompt = (
            f"Request: {user_request}\n"
            f"Type: {target_type}\n"
            f"Style: {style}\n"
            f"Audience: {target_audience}\n"
            f"Target words: {word_count}\n"
            f"Keywords: {', '.join(keywords) if keywords else user_request}\n\n"
            f"Learned style profile: {json.dumps(style_context)}\n\n"
            f"Related site context (for internal linking and voice consistency):\n"
            f"{json.dumps(related_context)[:3000]}"
        )
        planner_brain = self.brain.route("content_plan", len(plan_prompt), priority="speed")
        plan_raw = self.brain.generate(
            brain_name=planner_brain,
            prompt=plan_prompt,
            system_prompt=PIPELINE_PLAN_PROMPT,
        )
        plan_default = {
            "title": user_request[:80],
            "slug": self._safe_slug(user_request[:80]),
            "focus_keyword": primary_keyword,
            "secondary_keywords": keywords,
            "search_intent": "informational",
            "audience": target_audience,
            "outline": [],
            "faq_questions": [],
            "internal_link_topics": [],
        }
        plan = self._extract_json_object(plan_raw, plan_default)

        # 2) Write with quality model
        writer_prompt = (
            "Write a publish-ready educational WordPress article/page using the approved plan. "
            "Return clean HTML only. Include strong intro, rich sections, examples, FAQ, and CTA.\n\n"
            f"Plan JSON:\n{json.dumps(plan)}\n\n"
            f"Related site context:\n{json.dumps(related_context)[:3000]}\n\n"
            f"Style profile:\n{json.dumps(style_context)}\n\n"
            f"Mandatory constraints: target {word_count} words, audience={target_audience}, style={style}."
        )
        writer_brain = self.brain.route("create_content", len(writer_prompt), priority="quality")
        draft = self._clean_code_fences(
            self.brain.generate(
                brain_name=writer_brain,
                prompt=writer_prompt,
                system_prompt=BLOG_POST_SYSTEM_PROMPT,
            )
        )

        # 3) Critique with analytic model
        critic_prompt = (
            f"User request: {user_request}\n\n"
            f"Plan:\n{json.dumps(plan)}\n\n"
            f"Draft HTML:\n{draft[:8000]}"
        )
        critic_brain = self.brain.route("seo_optimize", len(critic_prompt), priority="quality")
        critique_raw = self.brain.generate(
            brain_name=critic_brain,
            prompt=critic_prompt,
            system_prompt=PIPELINE_CRITIC_PROMPT,
        )
        critique_default = {
            "seo_score": 0,
            "readability_score": 0,
            "depth_score": 0,
            "uniqueness_score": 0,
            "factual_confidence": 0,
            "weak_sections": [],
            "rewrite_instructions": ["Improve clarity and structure."],
        }
        critique = self._extract_json_object(critique_raw, critique_default)

        # 4) Rewrite if gate fails
        final_html = draft
        rewrites = 0
        if not self._passes_quality_gate(critique):
            rewrite_prompt = (
                f"User request: {user_request}\n\n"
                f"Plan:\n{json.dumps(plan)}\n\n"
                f"Critique:\n{json.dumps(critique)}\n\n"
                f"Draft HTML:\n{draft[:10000]}"
            )
            rewrite_brain = self.brain.route("update_content", len(rewrite_prompt), priority="quality")
            final_html = self._clean_code_fences(
                self.brain.generate(
                    brain_name=rewrite_brain,
                    prompt=rewrite_prompt,
                    system_prompt=PIPELINE_REWRITE_PROMPT,
                )
            )
            rewrites = 1

            # Re-score after rewrite
            recritic_prompt = (
                f"User request: {user_request}\n\n"
                f"Plan:\n{json.dumps(plan)}\n\n"
                f"Rewritten HTML:\n{final_html[:8000]}"
            )
            critique_raw = self.brain.generate(
                brain_name=critic_brain,
                prompt=recritic_prompt,
                system_prompt=PIPELINE_CRITIC_PROMPT,
            )
            critique = self._extract_json_object(critique_raw, critique)

        title = plan.get("title") or user_request[:80]
        slug = plan.get("slug") or self._safe_slug(title)
        focus_keyword = plan.get("focus_keyword") or primary_keyword
        assets = self._build_publish_assets(
            topic=user_request,
            title=title,
            slug=slug,
            keyword=focus_keyword,
            content_html=final_html,
            related_context=related_context,
        )

        return {
            "title": title,
            "slug": slug,
            "content": final_html,
            "meta_description": assets.get("meta_description", ""),
            "tags": assets.get("tags", []),
            "faq": assets.get("faq", []),
            "internal_links": assets.get("internal_links", []),
            "schema_faq_jsonld": assets.get("schema_faq_jsonld", ""),
            "keywords": keywords,
            "focus_keyword": focus_keyword,
            "word_count_target": word_count,
            "status": "draft",
            "quality_report": critique,
            "quality_passed": self._passes_quality_gate(critique),
            "rewrite_passes": rewrites,
            "plan": plan,
            "related_context": related_context,
            "generated_at": datetime.utcnow().isoformat(),
        }

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
        result = self.generate_power_content(
            user_request=topic,
            target_type="post",
            keywords=keywords or [],
            word_count=word_count,
            style=style,
            target_audience=target_audience,
        )
        return {
            "title": result.get("title", topic),
            "content": result.get("content", ""),
            "meta_description": result.get("meta_description", ""),
            "slug": result.get("slug", self._safe_slug(topic)),
            "keywords": result.get("keywords", keywords or []),
            "word_count_target": word_count,
            "status": "draft",
            "quality_report": result.get("quality_report", {}),
            "quality_passed": result.get("quality_passed", False),
            "faq": result.get("faq", []),
            "internal_links": result.get("internal_links", []),
            "schema_faq_jsonld": result.get("schema_faq_jsonld", ""),
            "plan": result.get("plan", {}),
            "related_context": result.get("related_context", []),
            "rewrite_passes": result.get("rewrite_passes", 0),
        }

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
