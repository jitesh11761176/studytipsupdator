"""Scheduler for StudyTips AI Agent automated tasks.

Runs morning routines, weekly content suggestions, stale content checks,
monthly SEO audits, and daily ranking updates.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import schedule

logger = logging.getLogger(__name__)


def _get_agent() -> Any:
    """Create and return a configured agent instance."""
    from agent.core.orchestrator import StudyTipsAgent
    return StudyTipsAgent()


def _notify(message: str, priority: str = "low") -> None:
    """Send admin notification."""
    try:
        from agent.core.config import load_config
        from agent.interfaces.notifications import NotificationService

        config = load_config()
        notifier = NotificationService(
            telegram_token=config.telegram.bot_token,
            admin_chat_id=config.telegram.admin_chat_id,
        )
        notifier.notify_admin(message, priority=priority)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Notification failed: %s", exc)


def morning_routine() -> None:
    """Daily morning routine: health check, broken links, ranking changes."""
    logger.info("Running morning routine...")
    try:
        agent = _get_agent()

        health = agent.check_site_health()
        score = health.get("score", "N/A")
        critical = len(health.get("critical", []))

        from agent.modules.seo_optimizer import SEOOptimizer
        from agent.core.brain_router import BrainRouter
        from agent.core.config import load_config

        config = load_config()
        brain = BrainRouter(config=config)
        seo = SEOOptimizer(brain_router=brain, config=config)
        ranking_changes = seo.check_ranking_changes()

        priority = "high" if critical > 0 else "low"
        message = (
            f"☀️ Morning Report\n\n"
            f"Site Health Score: {score}/100\n"
            f"Critical Issues: {critical}\n"
            f"Ranking data rows: {len(ranking_changes)}"
        )
        _notify(message, priority=priority)
    except Exception as exc:  # noqa: BLE001
        logger.error("Morning routine failed: %s", exc)
        _notify(f"Morning routine error: {exc}", priority="high")


def weekly_content_suggestions() -> None:
    """Monday routine: suggest 5 content topics."""
    logger.info("Generating weekly content suggestions...")
    try:
        from agent.core.config import load_config
        from agent.core.brain_router import BrainRouter
        from agent.modules.content_engine import ContentEngine

        config = load_config()
        brain = BrainRouter(config=config)
        engine = ContentEngine(brain_router=brain, config=config)
        topics = engine.suggest_topics(count=5)

        topics_text = "\n".join(f"• {t}" for t in topics)
        _notify(f"📝 Weekly Topic Suggestions:\n\n{topics_text}", priority="low")
    except Exception as exc:  # noqa: BLE001
        logger.error("Weekly content suggestions failed: %s", exc)


def stale_content_check() -> None:
    """Wednesday routine: find posts needing updates."""
    logger.info("Checking for stale content...")
    try:
        from agent.core.config import load_config
        from agent.core.brain_router import BrainRouter
        from agent.modules.content_engine import ContentEngine

        config = load_config()
        brain = BrainRouter(config=config)
        engine = ContentEngine(brain_router=brain, config=config)
        stale = engine.find_stale_posts(older_than_days=180)

        if stale:
            items = "\n".join(f"• {p['title'][:50]}" for p in stale[:5])
            _notify(f"♻️ Stale Content ({len(stale)} posts):\n\n{items}", priority="low")
        else:
            logger.info("No stale content found")
    except Exception as exc:  # noqa: BLE001
        logger.error("Stale content check failed: %s", exc)


def monthly_seo_audit() -> None:
    """1st of month: full SEO audit."""
    logger.info("Running monthly SEO audit...")
    try:
        from agent.core.config import load_config
        from agent.modules.site_auditor import SiteAuditor

        config = load_config()
        auditor = SiteAuditor(config=config)
        report = auditor.generate_audit_report()
        _notify(f"📊 Monthly SEO Audit:\n\n{report[:1000]}", priority="medium")
    except Exception as exc:  # noqa: BLE001
        logger.error("Monthly SEO audit failed: %s", exc)


def daily_ranking_update() -> None:
    """1 AM daily: update keyword rankings."""
    logger.info("Updating keyword rankings...")
    try:
        from agent.core.config import load_config
        from agent.core.brain_router import BrainRouter
        from agent.modules.seo_optimizer import SEOOptimizer

        config = load_config()
        brain = BrainRouter(config=config)
        seo = SEOOptimizer(brain_router=brain, config=config)
        changes = seo.check_ranking_changes()
        logger.info("Ranking update: %d rows", len(changes))
    except Exception as exc:  # noqa: BLE001
        logger.error("Daily ranking update failed: %s", exc)


def setup_schedule() -> None:
    """Configure all scheduled tasks."""
    schedule.every().day.at("06:00").do(morning_routine)
    schedule.every().monday.at("08:00").do(weekly_content_suggestions)
    schedule.every().wednesday.at("10:00").do(stale_content_check)
    schedule.every(1).months.do(monthly_seo_audit)  # type: ignore[attr-defined]
    schedule.every().day.at("01:00").do(daily_ranking_update)
    logger.info("Schedule configured")


def run_scheduler() -> None:
    """Main scheduler loop. Runs indefinitely."""
    setup_schedule()
    logger.info("Scheduler started. Running pending jobs then entering loop...")

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    run_scheduler()
