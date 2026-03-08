"""OpenRouter API client supporting multiple LLM models."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

SUPPORTED_MODELS = [
    "anthropic/claude-3.5-sonnet",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "meta-llama/llama-3.1-8b-instruct",
    "meta-llama/llama-3.1-70b-instruct",
    "google/gemini-2.0-flash-001",
]


class OpenRouterClient:
    """OpenRouter API client with retry and rate-limit handling.

    Args:
        api_key: OpenRouter API key.
        default_model: Model to use when none is specified.
        max_retries: Number of retry attempts on transient errors.
    """

    def __init__(
        self,
        api_key: str,
        default_model: str = "anthropic/claude-3.5-sonnet",
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.max_retries = max_retries
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://studytips.in",
                "X-Title": "StudyTips AI Agent",
                "Content-Type": "application/json",
            }
        )

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """Call the OpenRouter chat completions endpoint.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model: Model identifier. Uses default_model if not specified.
            temperature: Sampling temperature (0–2).
            max_tokens: Maximum tokens in the response.
            **kwargs: Additional parameters forwarded to the API.

        Returns:
            Assistant response text.

        Raises:
            requests.HTTPError: On persistent API errors.
        """
        model = model or self.default_model
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }

        for attempt in range(self.max_retries):
            try:
                response = self._session.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    json=payload,
                    timeout=60,
                )
                if response.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning("Rate limited, waiting %ds", wait)
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt == self.max_retries - 1:
                    raise
                logger.warning("Attempt %d failed: %s", attempt + 1, exc)
                time.sleep(2 ** attempt)

        raise RuntimeError("OpenRouter: exceeded max retries")
