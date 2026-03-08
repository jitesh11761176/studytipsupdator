"""Kimi (Moonshot AI) API client with 128K context support."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

KIMI_API_BASE = "https://api.moonshot.cn/v1"
KIMI_DEFAULT_MODEL = "moonshot-v1-128k"


class KimiClient:
    """Kimi / Moonshot AI API client.

    Particularly useful for long-context tasks (128K tokens).

    Args:
        api_key: Kimi API key (KIMI_API_KEY).
        max_retries: Number of retry attempts.
    """

    def __init__(self, api_key: str, max_retries: int = 3) -> None:
        self.api_key = api_key
        self.max_retries = max_retries
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        )

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = KIMI_DEFAULT_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """Call the Kimi chat completions endpoint.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model: Model name ('moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k').
            temperature: Sampling temperature.
            max_tokens: Maximum response tokens.
            **kwargs: Additional parameters.

        Returns:
            Assistant response text.
        """
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
                    f"{KIMI_API_BASE}/chat/completions",
                    json=payload,
                    timeout=120,
                )
                if response.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning("Kimi rate limited, waiting %ds", wait)
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt == self.max_retries - 1:
                    raise
                logger.warning("Kimi attempt %d failed: %s", attempt + 1, exc)
                time.sleep(2 ** attempt)

        raise RuntimeError("KimiClient: exceeded max retries")
