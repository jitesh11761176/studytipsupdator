"""GitHub Copilot Models API client."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

COPILOT_API_BASE = "https://api.githubcopilot.com"
COPILOT_DEFAULT_MODEL = "gpt-4o"


class CopilotClient:
    """GitHub Copilot Models API client.

    Uses the OpenAI-compatible endpoint exposed by GitHub Copilot.
    Automatically obtains and refreshes short-lived Copilot API tokens
    from the stored GitHub OAuth token (set via device-flow login).

    Args:
        token: GitHub OAuth token (GITHUB_COPILOT_TOKEN).  If blank, the
               module-level CopilotTokenManager is used to get a fresh
               Copilot token automatically.
        max_retries: Number of retry attempts.
    """

    def __init__(self, token: str = "", max_retries: int = 3) -> None:
        self._github_token = token
        self.max_retries = max_retries
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Editor-Version": "vscode/1.90.0",
            }
        )

    def _get_auth_header(self) -> str:
        """Return a valid Bearer token for the current request.

        Tries the token manager first (auto-refresh via OAuth token stored
        in .env), then falls back to the raw token passed at construction.
        """
        try:
            from agent.integrations.copilot_auth import get_token as _get_token
            managed = _get_token()
            if managed:
                return f"Bearer {managed}"
        except Exception:
            pass
        # Fallback: use the raw token as-is (may be a PAT or Copilot token)
        return f"Bearer {self._github_token}"

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = COPILOT_DEFAULT_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """Call the Copilot chat completions endpoint.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model: Copilot model name.
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
                self._session.headers["Authorization"] = self._get_auth_header()
                response = self._session.post(
                    f"{COPILOT_API_BASE}/chat/completions",
                    json=payload,
                    timeout=60,
                )
                if response.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning("Copilot rate limited, waiting %ds", wait)
                    time.sleep(wait)
                    continue
                if response.status_code >= 400:
                    logger.warning("Copilot API error %s: %s", response.status_code, response.text[:300])
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt == self.max_retries - 1:
                    raise
                logger.warning("Copilot attempt %d failed: %s", attempt + 1, exc)
                time.sleep(2 ** attempt)

        raise RuntimeError("CopilotClient: exceeded max retries")
