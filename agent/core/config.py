"""Configuration loader for StudyTips AI Agent.

Loads all environment variables and provides typed config dataclasses.
"""

import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class WPConfig:
    """WordPress site configuration."""

    site_url: str = ""
    username: str = ""
    app_password: str = ""
    api_base: str = ""

    def __post_init__(self) -> None:
        self.site_url = os.getenv("WP_SITE_URL", "https://studytips.in")
        self.username = os.getenv("WP_USERNAME", "")
        self.app_password = os.getenv("WP_APP_PASSWORD", "")
        self.api_base = f"{self.site_url}/wp-json/wp/v2"


@dataclass
class LLMConfig:
    """LLM API key configuration."""

    openrouter_api_key: str = ""
    github_copilot_token: str = ""
    github_token: str = ""
    nvidia_api_key: str = ""
    kimi_api_key: str = ""
    ollama_host: str = ""
    ollama_model: str = ""

    def __post_init__(self) -> None:
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.github_copilot_token = os.getenv("GITHUB_COPILOT_TOKEN", "")
        self.github_token = os.getenv("GITHUB_TOKEN", "")
        self.nvidia_api_key = os.getenv("NVIDIA_API_KEY", "")
        self.kimi_api_key = os.getenv("KIMI_API_KEY", "")
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2")


@dataclass
class GoogleConfig:
    """Google APIs configuration."""

    analytics_property_id: str = ""
    search_console_site: str = ""
    service_account_key: str = ""

    def __post_init__(self) -> None:
        self.analytics_property_id = os.getenv("GOOGLE_ANALYTICS_PROPERTY_ID", "")
        self.search_console_site = os.getenv(
            "GOOGLE_SEARCH_CONSOLE_SITE", "https://studytips.in"
        )
        self.service_account_key = os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY", "")


@dataclass
class TelegramConfig:
    """Telegram bot configuration."""

    bot_token: str = ""
    admin_chat_id: str = ""

    def __post_init__(self) -> None:
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.admin_chat_id = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "")


@dataclass
class AgentConfig:
    """Agent behaviour configuration."""

    mode: str = "interactive"
    default_post_status: str = "draft"
    content_language: str = "en"
    memory_db_path: str = "data/memory.db"
    content_calendar_path: str = "data/content_calendar.json"
    custom_brains_db_path: str = "data/memory.db"

    def __post_init__(self) -> None:
        self.mode = os.getenv("AGENT_MODE", "interactive")
        self.default_post_status = os.getenv("DEFAULT_POST_STATUS", "draft")
        self.content_language = os.getenv("CONTENT_LANGUAGE", "en")
        self.memory_db_path = os.getenv("MEMORY_DB_PATH", "data/memory.db")
        self.content_calendar_path = os.getenv(
            "CONTENT_CALENDAR_PATH", "data/content_calendar.json"
        )
        self.custom_brains_db_path = os.getenv(
            "CUSTOM_BRAINS_DB_PATH", self.memory_db_path
        )


@dataclass
class AppConfig:
    """Top-level application config bundling all sub-configs."""

    wp: WPConfig = field(default_factory=WPConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    google: GoogleConfig = field(default_factory=GoogleConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)


def load_config() -> AppConfig:
    """Load and return the full application configuration.

    Returns:
        AppConfig: Populated configuration object.
    """
    return AppConfig(
        wp=WPConfig(),
        llm=LLMConfig(),
        google=GoogleConfig(),
        telegram=TelegramConfig(),
        agent=AgentConfig(),
    )
