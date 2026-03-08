"""NVIDIA NIM API client — universal gateway for all NVIDIA-hosted models."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

NVIDIA_API_BASE = "https://integrate.api.nvidia.com/v1"
NVIDIA_DEFAULT_MODEL = "nvidia/llama-3.1-nemotron-70b-instruct"

# Popular models available through the NVIDIA API
NVIDIA_AVAILABLE_MODELS: List[str] = [
    "moonshotai/kimi-k2.5",
    "meta/llama-3.3-70b-instruct",
    "google/gemma-2-27b-it",
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "deepseek-ai/deepseek-r1",
    "microsoft/phi-3-medium-128k-instruct",
    "mistralai/mistral-large-2-instruct",
]


class NvidiaClient:
    """NVIDIA NIM API client (OpenAI-compatible).

    Supports any model available on the NVIDIA API gateway, not just the
    default nemotron model.

    Args:
        api_key: NVIDIA API key (NVIDIA_API_KEY).
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
                "Accept": "application/json",
            }
        )

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = NVIDIA_DEFAULT_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 16384,
        top_p: float = 1.0,
        **kwargs: Any,
    ) -> str:
        """Call the NVIDIA NIM chat completions endpoint.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model: NIM model identifier (any model hosted on NVIDIA API).
            temperature: Sampling temperature.
            max_tokens: Maximum response tokens (up to 16384+).
            top_p: Top-p nucleus sampling parameter.
            **kwargs: Additional parameters forwarded to the API.

        Returns:
            Assistant response text.
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            **kwargs,
        }

        for attempt in range(self.max_retries):
            try:
                response = self._session.post(
                    f"{NVIDIA_API_BASE}/chat/completions",
                    json=payload,
                    timeout=120,
                )
                if response.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning("NVIDIA rate limited, waiting %ds", wait)
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                data = response.json()
                message = data["choices"][0]["message"]
                # Kimi K2.5 and other reasoning models return content in
                # reasoning_content when content is null
                return message.get("content") or message.get("reasoning_content") or ""
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt == self.max_retries - 1:
                    raise
                logger.warning("NVIDIA attempt %d failed: %s", attempt + 1, exc)
                time.sleep(2 ** attempt)

        raise RuntimeError("NvidiaClient: exceeded max retries")

    def list_available_models(self) -> List[str]:
        """Return the list of known NVIDIA-hosted models.

        Returns:
            List of model identifier strings available through the NVIDIA API.
        """
        return list(NVIDIA_AVAILABLE_MODELS)
