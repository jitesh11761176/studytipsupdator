"""Local Ollama API client for on-device LLM inference."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class OllamaClient:
    """Client for the local Ollama inference server.

    Args:
        host: Base URL of the Ollama server (default: http://localhost:11434).
        default_model: Model name to use when none specified.
    """

    def __init__(
        self,
        host: str = "http://localhost:11434",
        default_model: str = "llama3.2",
    ) -> None:
        self.host = host.rstrip("/")
        self.default_model = default_model

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """Call the Ollama /api/chat endpoint.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model: Ollama model name. Uses default_model if omitted.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens (passed as num_predict option).
            **kwargs: Additional Ollama options.

        Returns:
            Model response text.
        """
        model = model or self.default_model
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                **kwargs,
            },
        }
        response = requests.post(
            f"{self.host}/api/chat",
            json=payload,
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"]

    def list_models(self) -> List[Dict[str, Any]]:
        """List all locally available Ollama models.

        Returns:
            List of model info dicts.
        """
        response = requests.get(f"{self.host}/api/tags", timeout=10)
        response.raise_for_status()
        return response.json().get("models", [])

    def pull_model(self, model_name: str) -> bool:
        """Pull a model from the Ollama registry.

        Args:
            model_name: Model name/tag to pull (e.g. 'llama3.2').

        Returns:
            True if pull completed successfully.
        """
        logger.info("Pulling Ollama model: %s", model_name)
        response = requests.post(
            f"{self.host}/api/pull",
            json={"name": model_name, "stream": False},
            timeout=600,
        )
        response.raise_for_status()
        return True
