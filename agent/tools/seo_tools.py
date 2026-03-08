"""SEO action tools for agent function calling."""

from __future__ import annotations

from typing import Any, Dict


def _run_seo_audit(url: str) -> Dict[str, Any]:
    """Execute SEO audit."""
    from agent.core.config import load_config
    from agent.core.brain_router import BrainRouter
    from agent.modules.seo_optimizer import SEOOptimizer

    config = load_config()
    brain = BrainRouter(config=config)
    optimizer = SEOOptimizer(brain_router=brain, config=config)
    return optimizer.audit_page_seo(url)


run_seo_audit_tool: Dict[str, Any] = {
    "name": "run_seo_audit",
    "description": "Run a comprehensive SEO audit on a specific page URL",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Full URL of the page to audit"},
        },
        "required": ["url"],
    },
    "execute": _run_seo_audit,
}


def _optimize_page_seo(post_id_or_url: str) -> Dict[str, Any]:
    """Execute page SEO optimisation."""
    from agent.core.config import load_config
    from agent.core.brain_router import BrainRouter
    from agent.modules.seo_optimizer import SEOOptimizer

    config = load_config()
    brain = BrainRouter(config=config)
    optimizer = SEOOptimizer(brain_router=brain, config=config)
    return optimizer.optimize_post(post_id_or_url)


optimize_page_seo_tool: Dict[str, Any] = {
    "name": "optimize_page_seo",
    "description": "Generate SEO improvements for a WordPress post or page",
    "parameters": {
        "type": "object",
        "properties": {
            "post_id_or_url": {"type": "string", "description": "Post ID or URL to optimise"},
        },
        "required": ["post_id_or_url"],
    },
    "execute": _optimize_page_seo,
}


def _research_keywords(topic: str) -> Dict[str, Any]:
    """Execute keyword research."""
    from agent.core.config import load_config
    from agent.core.brain_router import BrainRouter
    from agent.modules.seo_optimizer import SEOOptimizer

    config = load_config()
    brain = BrainRouter(config=config)
    optimizer = SEOOptimizer(brain_router=brain, config=config)
    return optimizer.keyword_research(topic)


research_keywords_tool: Dict[str, Any] = {
    "name": "research_keywords",
    "description": "Research keywords and SEO opportunities for a given topic",
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Topic or seed keyword to research"},
        },
        "required": ["topic"],
    },
    "execute": _research_keywords,
}
