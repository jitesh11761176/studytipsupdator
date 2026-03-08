"""Telegram bot interface for controlling the agent from a phone."""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def create_telegram_bot() -> Optional[object]:
    """Create and configure the Telegram bot application.

    Requires TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_CHAT_ID environment variables.

    Returns:
        Telegram Application instance or None if telegram library unavailable.
    """
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
        from telegram.ext import (
            Application,
            CallbackQueryHandler,
            CommandHandler,
            ContextTypes,
            MessageHandler,
            filters,
        )
        from agent.core.orchestrator import StudyTipsAgent
        from agent.core.config import load_config
    except ImportError:
        logger.error("python-telegram-bot not installed. Run: pip install python-telegram-bot")
        return None

    config = load_config()
    bot_token = config.telegram.bot_token
    admin_chat_id = config.telegram.admin_chat_id

    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return None

    agent = StudyTipsAgent(config=config)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _is_admin(update: Update) -> bool:
        return str(update.effective_chat.id) == str(admin_chat_id)

    async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not _is_admin(update):
            return
        await update.message.reply_text(
            "👋 StudyTips AI Agent is online!\n\n"
            "Send me any instruction and I'll prepare a draft for your approval.\n\n"
            "Commands:\n"
            "/start — Show this message\n"
            "/help — Show available actions\n"
            "/audit — Run site health check\n"
            "/status — Show pending actions"
        )

    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not _is_admin(update):
            return
        await update.message.reply_text(
            "🤖 **Available Actions:**\n\n"
            "• Write a blog post about [topic]\n"
            "• Optimize SEO for [URL]\n"
            "• Run a full site audit\n"
            "• Generate content calendar for next month\n"
            "• Update [page URL] with [instructions]\n"
            "• Find stale content\n"
            "• Show analytics report",
            parse_mode="Markdown",
        )

    async def audit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not _is_admin(update):
            return
        await update.message.reply_text("🔍 Running site health check...")
        health = agent.check_site_health()
        score = health.get("score", "N/A")
        critical = len(health.get("critical", []))
        warnings = len(health.get("warnings", []))
        await update.message.reply_text(
            f"✅ **Site Health Report**\n\nScore: {score}/100\n"
            f"Critical: {critical}\nWarnings: {warnings}",
            parse_mode="Markdown",
        )

    async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not _is_admin(update):
            return
        pending = agent.get_pending_actions()
        if not pending:
            await update.message.reply_text("✅ No pending actions.")
        else:
            text = f"⏳ **{len(pending)} pending actions:**\n\n"
            for action in pending[:5]:
                text += f"• [{action['intent']}] ID:{action['action_id']}\n"
            await update.message.reply_text(text, parse_mode="Markdown")

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not _is_admin(update):
            return

        user_prompt = update.message.text
        await update.message.reply_text("⏳ Processing your request...")

        try:
            result = agent.process_prompt(user_prompt)
            formatted = result.get("formatted_output", "No output generated.")

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"approve:{result['action_id']}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"reject:{result['action_id']}"),
                ]
            ])

            # Telegram message limit: 4096 chars
            if len(formatted) > 3900:
                formatted = formatted[:3900] + "\n...[truncated]"

            await update.message.reply_text(
                formatted,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Agent error: %s", exc)
            await update.message.reply_text(f"❌ Error: {exc}")

    async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()

        if not _is_admin(update):
            return

        data = query.data
        if ":" not in data:
            return

        action, action_id_str = data.split(":", 1)
        action_id = int(action_id_str)

        # Find matching pending action
        pending = [a for a in agent._pending_actions if a["action_id"] == action_id]
        if not pending:
            await query.edit_message_text("❓ Action not found (may have already been processed).")
            return

        target_action = pending[0]

        if action == "approve":
            try:
                agent.execute_approved(target_action)
                await query.edit_message_text(f"✅ Action {action_id} approved and executed!")
            except Exception as exc:  # noqa: BLE001
                await query.edit_message_text(f"❌ Execution failed: {exc}")
        elif action == "reject":
            agent.learn_from_rejection(target_action, feedback="Rejected via Telegram")
            await query.edit_message_text(f"❌ Action {action_id} rejected. Agent will learn from this.")

    # ------------------------------------------------------------------
    # Build and return application
    # ------------------------------------------------------------------

    app = Application.builder().token(bot_token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("audit", audit_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    return app


def run_bot() -> None:
    """Start the Telegram bot in polling mode."""
    app = create_telegram_bot()
    if app is None:
        logger.error("Could not create Telegram bot")
        return
    logger.info("Starting Telegram bot...")
    app.run_polling()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_bot()
