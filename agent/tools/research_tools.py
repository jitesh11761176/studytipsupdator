"""Research tools for competitor analysis and trend discovery."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _analyze_competitor(competitor_url: str) -> Dict[str, Any]:
    """Execute competitor analysis."""
    import requests
    from agent.core.config import load_config
    from agent.core.brain_router import BrainRouter

    config = load_config()
    brain = BrainRouter(config=config)

    try:
        response = requests.get(competitor_url, timeout=10)
        html_excerpt = response.text[:3000]
    except Exception as exc:  # noqa: BLE001
        html_excerpt = f"Could not fetch: {exc}"

    prompt = (
        f"Analyse this competitor page for studytips.in:\n\nURL: {competitor_url}\n\n"
        f"Content excerpt:\n{html_excerpt}\n\n"
        "Provide: topic_coverage, content_gaps (what studytips.in could cover better), "
        "keyword_opportunities, and competitive_advantages to target. Return as JSON."
    )
    brain_name = brain.route("general", priority="quality")
    raw = brain.generate(brain_name=brain_name, prompt=prompt)

    import json
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end]) if start >= 0 else {"analysis": raw}
    except json.JSONDecodeError:
        return {"analysis": raw}


analyze_competitor_tool: Dict[str, Any] = {
    "name": "analyze_competitor",
    "description": "Analyse a competitor website for content gaps and keyword opportunities",
    "parameters": {
        "type": "object",
        "properties": {
            "competitor_url": {"type": "string", "description": "Competitor page URL to analyse"},
        },
        "required": ["competitor_url"],
    },
    "execute": _analyze_competitor,
}


def _find_trending_topics(niche: str = "study tips india") -> List[str]:
    """Find trending topic ideas."""
    from agent.core.config import load_config
    from agent.core.brain_router import BrainRouter

    config = load_config()
    brain = BrainRouter(config=config)

    prompt = (
        f"Identify 10 trending topics for the niche: '{niche}'.\n"
        "Focus on what Indian students are actively searching for right now. "
        "Consider current exam seasons, educational trends, and student pain points. "
        "Return as a JSON array of topic strings."
    )
    brain_name = brain.route("content_plan", priority="speed")
    raw = brain.generate(brain_name=brain_name, prompt=prompt)

    import json
    try:
        start = raw.find("[")
        end = raw.rfind("]") + 1
        return json.loads(raw[start:end]) if start >= 0 else []
    except json.JSONDecodeError:
        return []


find_trending_topics_tool: Dict[str, Any] = {
    "name": "find_trending_topics",
    "description": "Discover trending content topics for the Indian student audience",
    "parameters": {
        "type": "object",
        "properties": {
            "niche": {"type": "string", "description": "Niche to find trends for", "default": "study tips india"},
        },
        "required": [],
    },
    "execute": _find_trending_topics,
}
