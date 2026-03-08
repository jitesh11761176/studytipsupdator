"""Main orchestrator for StudyTips AI Agent.

The StudyTipsAgent class is the primary entry point. It analyses user intent,
creates an action plan, executes it, and presents results for human approval.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from agent.core.brain_router import BrainRouter
from agent.core.config import AppConfig, load_config
from agent.core.memory import AgentMemory

logger = logging.getLogger(__name__)

# Recognised intent types
INTENT_TYPES = [
    "create_content",
    "update_content",
    "seo_optimize",
    "design_update",
    "create_page",
    "site_audit",
    "content_plan",
    "analytics",
    "bulk_update",
    "keyword_research",
    "deep_crawl",
    "auto_link",
    "auto_fix",
    "design_analysis",
    "general",
]

INTENT_CLASSIFICATION_PROMPT = """You are an intent classifier for a WordPress management agent for studytips.in.

Given the user prompt below, classify it into exactly ONE of these intent types:
- create_content: write new blog post or article
- update_content: edit/update existing content
- seo_optimize: SEO, meta tags, keywords, schema
- design_update: CSS, layout, theme, UI suggestions
- create_page: create a new static page
- site_audit: health check, broken links, thin content
- content_plan: content calendar, topic planning
- analytics: traffic, performance data
- bulk_update: update multiple pages at once
- keyword_research: find keywords, search volume
- deep_crawl: full site scan, check all pages, find orphans/missing pages, site map
- auto_link: add internal links to drafts, link pages together, fix linking
- auto_fix: fix everything, auto-fix issues, process drafts, one-click improvements
- design_analysis: analyse actual site design, live CSS/HTML review, speed, UX
- general: anything else

Respond with ONLY the intent type string, no explanation.

User prompt: {prompt}"""

ACTION_PLAN_PROMPT = """You are a WordPress management agent for studytips.in.

Intent: {intent}
User request: {prompt}
Site style guide: {style_guide}

Create a concise, numbered step-by-step action plan to fulfil this request.
Each step should be a clear, actionable task.
Return a JSON array of strings, e.g.: ["Step 1: ...", "Step 2: ..."]"""


class StudyTipsAgent:
    """Autonomous AI agent for managing studytips.in WordPress site.

    Processes natural language prompts, creates action plans, executes them,
    and returns results for human approval before any changes go live.
    """

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        """Initialise the agent.

        Args:
            config: Optional pre-built AppConfig. Loads from environment if omitted.
        """
        self.config = config or load_config()
        self.memory = AgentMemory(db_path=self.config.agent.memory_db_path)
        self.brain = BrainRouter(config=self.config)
        self._tools: Dict[str, Any] = {}
        self._pending_actions: List[Dict[str, Any]] = []
        self._register_tools()

    def _wp_client(self) -> Any:
        """Return a fresh WordPressClient instance."""
        from agent.integrations.wordpress_api import WordPressClient
        return WordPressClient(config=self.config.wp)

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def _register_tools(self) -> None:
        """Register all available agent tools."""
        try:
            from agent.tools.wp_tools import (
                create_blog_post_tool,
                update_page_tool,
                upload_media_tool,
            )
            from agent.tools.seo_tools import (
                run_seo_audit_tool,
                optimize_page_seo_tool,
                research_keywords_tool,
            )
            from agent.tools.research_tools import (
                analyze_competitor_tool,
                find_trending_topics_tool,
            )
            from agent.tools.file_tools import read_file_tool, write_file_tool

            for tool in [
                create_blog_post_tool,
                update_page_tool,
                upload_media_tool,
                run_seo_audit_tool,
                optimize_page_seo_tool,
                research_keywords_tool,
                analyze_competitor_tool,
                find_trending_topics_tool,
                read_file_tool,
                write_file_tool,
            ]:
                self._tools[tool["name"]] = tool
            logger.info("Registered %d tools", len(self._tools))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tool registration partially failed: %s", exc)

    # ------------------------------------------------------------------
    # Core pipeline
    # ------------------------------------------------------------------

    def process_prompt(self, user_prompt: str) -> Dict[str, Any]:
        """Main entry point: analyse → plan → execute → format for approval.

        Args:
            user_prompt: Natural language instruction from the user.

        Returns:
            Dict with keys: intent, plan, results, formatted_output, action_id.
        """
        logger.info("Processing prompt: %s", user_prompt[:100])

        intent = self._analyze_intent(user_prompt)
        plan = self._create_action_plan(intent, user_prompt)
        results = self._execute_plan(plan, intent)

        action_id = self.memory.log_interaction(
            prompt=user_prompt,
            intent=intent,
            plan=plan,
            results=results,
        )

        formatted = self._format_for_approval(results, intent, plan)

        pending = {
            "action_id": action_id,
            "intent": intent,
            "plan": plan,
            "results": results,
            "formatted_output": formatted,
            "created_at": datetime.utcnow().isoformat(),
        }
        self._pending_actions.append(pending)

        return pending

    def _analyze_intent(self, prompt: str) -> str:
        """Classify the user's intent from natural language.

        Args:
            prompt: The raw user prompt.

        Returns:
            One of the INTENT_TYPES strings.
        """
        try:
            brain_name = self.brain.route("general", len(prompt), priority="speed")
            response = self.brain.generate(
                brain_name=brain_name,
                prompt=INTENT_CLASSIFICATION_PROMPT.format(prompt=prompt),
            ).strip().lower()

            # Validate and return; default to 'general' if unrecognised
            for intent in INTENT_TYPES:
                if intent in response:
                    return intent
        except Exception as exc:  # noqa: BLE001
            logger.warning("Intent classification failed: %s", exc)

        return "general"

    def _create_action_plan(
        self, intent: str, prompt: str
    ) -> List[str]:
        """Generate a step-by-step execution plan.

        Args:
            intent: Classified intent type.
            prompt: Original user prompt.

        Returns:
            List of action step strings.
        """
        style_guide = json.dumps(self.memory.get_style_guide())
        try:
            brain_name = self.brain.route(intent, priority="balanced")
            raw = self.brain.generate(
                brain_name=brain_name,
                prompt=ACTION_PLAN_PROMPT.format(
                    intent=intent, prompt=prompt, style_guide=style_guide
                ),
            ).strip()

            # Extract JSON array from response
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Action plan generation failed: %s", exc)

        # Fallback plan
        return [f"Process request: {prompt[:100]}"]

    def _execute_plan(
        self, plan: List[str], intent: str
    ) -> Dict[str, Any]:
        """Execute each step of the plan and collect results.

        Args:
            plan: List of step descriptions.
            intent: The classified intent (used for module routing).

        Returns:
            Dict with step results and any generated content/data.
        """
        results: Dict[str, Any] = {
            "steps": [],
            "status": "pending_approval",
            "draft_content": None,
            "metadata": {},
        }

        for i, step in enumerate(plan):
            step_result: Dict[str, Any] = {
                "step": i + 1,
                "description": step,
                "status": "planned",
                "output": None,
            }
            try:
                output = self._dispatch_step(step, intent)
                step_result["output"] = output
                step_result["status"] = "completed"
            except Exception as exc:  # noqa: BLE001
                logger.warning("Step %d failed: %s", i + 1, exc)
                step_result["status"] = "failed"
                step_result["output"] = str(exc)

            results["steps"].append(step_result)

        # Aggregate draft content from steps
        drafts = [
            s["output"]
            for s in results["steps"]
            if s.get("output") and isinstance(s["output"], str)
        ]
        if drafts:
            results["draft_content"] = "\n\n".join(drafts)

        return results

    def _dispatch_step(self, step: str, intent: str) -> Any:
        """Dispatch a single plan step to the appropriate module.

        Args:
            step: Step description string.
            intent: Overall intent for context.

        Returns:
            Output from the step execution.
        """
        step_lower = step.lower()

        # === SitePower module (deep crawl, auto-link, auto-fix, design) ===
        if intent == "deep_crawl" or any(kw in step_lower for kw in ["crawl", "scan all", "check all pages", "site map", "orphan", "missing page"]):
            from agent.modules.site_power import SitePower
            power = SitePower(brain_router=self.brain, config=self.config)
            return json.dumps(power.full_power_report(), indent=2, default=str)

        if intent == "auto_link" or any(kw in step_lower for kw in ["auto-link", "auto link", "internal link", "link draft"]):
            from agent.modules.site_power import SitePower
            power = SitePower(brain_router=self.brain, config=self.config)
            return json.dumps(power.auto_link_drafts(), indent=2, default=str)

        if intent == "auto_fix" or any(kw in step_lower for kw in ["auto-fix", "auto fix", "fix everything", "fix all"]):
            from agent.modules.site_power import SitePower
            power = SitePower(brain_router=self.brain, config=self.config)
            return json.dumps(power.auto_fix_all(), indent=2, default=str)

        if intent == "design_analysis" or any(kw in step_lower for kw in ["design analys", "ui review", "ux review", "css review", "live design"]):
            from agent.modules.site_power import SitePower
            power = SitePower(brain_router=self.brain, config=self.config)
            return json.dumps(power.analyze_design(), indent=2, default=str)

        # === Content creation ===
        if any(kw in step_lower for kw in ["write", "generate", "draft", "create post", "create article"]):
            from agent.modules.content_engine import ContentEngine
            engine = ContentEngine(brain_router=self.brain, config=self.config)
            return engine.generate_outline(topic=step, keywords=[])

        # === Page creation (with auto-parent detection) ===
        if intent == "create_page" or any(kw in step_lower for kw in ["create page", "new page"]):
            from agent.modules.site_power import SitePower
            power = SitePower(brain_router=self.brain, config=self.config)
            # Extract title from step
            title = step.replace("create page", "").replace("new page", "").strip().strip('"\'')
            if not title:
                title = step
            brain_name = self.brain.route("create_content", priority="quality")
            content = self.brain.generate(
                brain_name=brain_name,
                prompt=(
                    f"Create a comprehensive page for studytips.in titled '{title}'.\n"
                    "Write 500-800 words of SEO-optimised HTML. Include H2 headings, bullet points, CTA.\n"
                    "Return only HTML content."
                ),
            )
            import re as _re
            content = _re.sub(r'^```(?:html)?\s*\n?', '', content.strip())
            content = _re.sub(r'\n?```\s*$', '', content.strip())
            wp = self._wp_client()
            pages = power._fetch_all(wp, "pages", "publish")
            parent_id = power._find_best_parent(title, power._simplify_list(pages))
            created = wp.create_page(title=title, content=content, parent=parent_id, status="draft")
            return json.dumps({"created": True, "id": created.get("id"), "title": title, "parent_id": parent_id, "link": created.get("link", "")}, indent=2)

        # === SEO ===
        if any(kw in step_lower for kw in ["seo", "meta", "keyword", "optimize"]):
            from agent.modules.seo_optimizer import SEOOptimizer
            optimizer = SEOOptimizer(brain_router=self.brain, config=self.config)
            return optimizer.keyword_research(topic=step)

        # === Site audit ===
        if any(kw in step_lower for kw in ["audit", "check", "health"]):
            from agent.modules.site_auditor import SiteAuditor
            auditor = SiteAuditor(config=self.config)
            return auditor.generate_audit_report()

        # === Navigation / menu placement ===
        if any(kw in step_lower for kw in ["navigation", "menu", "place in nav", "tab"]):
            from agent.modules.site_power import SitePower
            power = SitePower(brain_router=self.brain, config=self.config)
            return json.dumps(power.place_drafts_in_nav(), indent=2, default=str)

        # Generic: use LLM to process the step
        brain_name = self.brain.route(intent, len(step), priority="balanced")
        return self.brain.generate(
            brain_name=brain_name,
            prompt=f"Execute this task for studytips.in WordPress site:\n{step}\n\nProvide the output as plain text.",
            system_prompt="You are an AI agent managing the studytips.in WordPress site. Always create drafts for human approval.",
        )

    def _format_for_approval(
        self,
        results: Dict[str, Any],
        intent: str,
        plan: List[str],
    ) -> str:
        """Format execution results for human review.

        Args:
            results: Execution results dict.
            intent: Classified intent.
            plan: Original action plan.

        Returns:
            Formatted string ready to present to the user.
        """
        lines = [
            f"🤖 **StudyTips Agent** — Action Plan ({intent})",
            "",
            "**Steps completed:**",
        ]
        for step in results.get("steps", []):
            status_icon = "✅" if step["status"] == "completed" else "❌"
            lines.append(f"  {status_icon} Step {step['step']}: {step['description']}")
            if step.get("output"):
                preview = str(step["output"])[:200]
                lines.append(f"     → {preview}{'...' if len(str(step['output'])) > 200 else ''}")

        if results.get("draft_content"):
            lines += [
                "",
                "**Draft Content Preview:**",
                "```",
                results["draft_content"][:500],
                "```",
            ]

        lines += [
            "",
            "─" * 50,
            "**[A] Approve & Publish  |  [R] Reject  |  [E] Edit**",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Approval workflow
    # ------------------------------------------------------------------

    def execute_approved(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Execute approved actions (publish drafts, apply changes).

        Args:
            response: The pending action dict returned by process_prompt.

        Returns:
            Dict with execution results.

        Raises:
            RuntimeError: When WordPress publishing fails.
        """
        action_id = response.get("action_id")
        intent = response.get("intent", "general")
        results = response.get("results", {})

        self.memory.record_feedback(action_id=action_id, approved=True)

        # If there is draft content, attempt to publish via WordPress
        if results.get("draft_content"):
            from agent.integrations.wordpress_api import WordPressClient
            wp = WordPressClient(config=self.config.wp)

            # Use actual title/slug from results (Content Studio passes these)
            title = results.get("title") or f"Draft — {intent}"
            slug = results.get("slug") or ""
            status = self.config.agent.default_post_status

            # Determine post vs page: explicit publish_as > intent-based
            publish_as = results.pop("publish_as", None)
            use_page = publish_as == "page" or (
                publish_as is None and intent in ("create_page", "update_page")
            )

            try:
                if use_page:
                    # Wrap content with padding for full-width Elementor layout
                    padded = (
                        '<div style="padding:50px 120px;">'
                        + results["draft_content"]
                        + '</div>'
                    )
                    created = wp.create_page(
                        title=title,
                        content=padded,
                        slug=slug,
                        status=status,
                        template="elementor_header_footer",
                    )
                    # Set Elementor full-width metadata so Elementor
                    # opens the page in its builder with full width.
                    page_id = created.get("id")
                    if page_id:
                        try:
                            wp.update_page(page_id, meta={
                                "_elementor_edit_mode": "builder",
                                "_elementor_template_type": "wp-page",
                            })
                        except Exception:
                            pass  # non-critical — template is already set
                else:
                    created = wp.create_post(
                        title=title,
                        content=results["draft_content"],
                        slug=slug,
                        status=status,
                    )

                results["published_post"] = created
                logger.info(
                    "Published %s id=%s title='%s' status='%s'",
                    "page" if intent in ("create_page", "update_page") else "post",
                    created.get("id"),
                    title,
                    status,
                )

                self.memory.add_winning_strategy(
                    strategy_type=intent,
                    description=f"Successful {intent} action",
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to publish: %s", exc)
                results["publish_error"] = str(exc)
                raise RuntimeError(
                    f"WordPress publish failed: {exc}\n\n"
                    "Make sure WP_USERNAME and WP_APP_PASSWORD are set "
                    "correctly in your .env file."
                ) from exc

        results["status"] = "approved"
        return results

    def learn_from_rejection(
        self, response: Dict[str, Any], feedback: str = ""
    ) -> None:
        """Record rejection and update learning memory.

        Args:
            response: The pending action dict.
            feedback: Optional free-text user feedback.
        """
        action_id = response.get("action_id")
        self.memory.record_feedback(
            action_id=action_id, approved=False, feedback=feedback
        )
        if feedback:
            from agent.learning.style_learner import StyleLearner
            learner = StyleLearner(memory=self.memory)
            learner.learn_from_feedback(feedback=feedback, approved=False)

    def get_pending_actions(self) -> List[Dict[str, Any]]:
        """Return all pending draft actions awaiting approval.

        Returns:
            List of pending action dicts.
        """
        return [a for a in self._pending_actions if a["results"].get("status") == "pending_approval"]

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    def check_site_health(self) -> Dict[str, Any]:
        """Run a quick site health check.

        Returns:
            Dict with health status summary.
        """
        try:
            from agent.modules.site_auditor import SiteAuditor
            auditor = SiteAuditor(config=self.config)
            return auditor.full_audit()
        except Exception as exc:  # noqa: BLE001
            logger.error("Site health check failed: %s", exc)
            return {"status": "error", "error": str(exc)}

    def generate_daily_report(self) -> str:
        """Generate a daily summary report for the admin.

        Returns:
            Formatted report string.
        """
        recent = self.memory.get_recent_interactions(limit=5)
        lines = [
            f"📊 **Daily Report — {datetime.utcnow().strftime('%Y-%m-%d')}**",
            "",
            f"Recent interactions: {len(recent)}",
        ]
        for interaction in recent:
            approved_label = (
                "✅" if interaction.get("approved") == 1
                else "❌" if interaction.get("approved") == 0
                else "⏳"
            )
            lines.append(
                f"  {approved_label} [{interaction['intent']}] {interaction['prompt'][:60]}"
            )
        return "\n".join(lines)
