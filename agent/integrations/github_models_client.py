"""GitHub Models API client (GitHub Student Developer Pack)."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

GITHUB_MODELS_ENDPOINT = "https://models.inference.ai.azure.com"
# Note: GitHub Models API is hosted on Azure infrastructure as part of
# the GitHub Student Developer Pack / GitHub Copilot offering.
# The endpoint uses an Azure domain but is accessed with a GitHub token.


class GitHubModelsClient:
    """Client for GitHub Models API (Student Developer Pack).

    Uses the same token as GitHub Copilot to access models like:
    - gpt-4o, gpt-4o-mini
    - o1-preview, o1-mini
    - Mistral-large, Phi-4
    - Meta-Llama models
    - Cohere Command
    - AI21 Jamba

    Args:
        token: GitHub personal access token (GITHUB_TOKEN).
        max_retries: Number of retry attempts.
    """

    ENDPOINT = GITHUB_MODELS_ENDPOINT

    AVAILABLE_MODELS: List[str] = [
        "gpt-4o",
        "gpt-4o-mini",
        "o1-preview",
        "o1-mini",
        "Mistral-large-2411",
        "Phi-4",
        "AI21-Jamba-1.5-Large",
        "Cohere-command-r-plus-08-2024",
        "Meta-Llama-3.1-405B-Instruct",
    ]

    def __init__(self, token: str, max_retries: int = 3) -> None:
        self.token = token
        self.max_retries = max_retries
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4o",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """Call the GitHub Models chat completions endpoint.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model: GitHub Models model identifier.
            temperature: Sampling temperature.
            max_tokens: Maximum response tokens.
            **kwargs: Additional parameters forwarded to the API.

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
                    f"{self.ENDPOINT}/chat/completions",
                    json=payload,
                    timeout=60,
                )
                if response.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning("GitHub Models rate limited, waiting %ds", wait)
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt == self.max_retries - 1:
                    raise
                logger.warning(
                    "GitHub Models attempt %d failed: %s", attempt + 1, exc
                )
                time.sleep(2 ** attempt)

        raise RuntimeError("GitHubModelsClient: exceeded max retries")

    def list_available_models(self) -> List[str]:
        """Return the list of models available through GitHub Models API.

        Returns:
            List of model identifier strings.
        """
        return list(self.AVAILABLE_MODELS)
