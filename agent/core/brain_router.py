"""Multi-LLM brain router for StudyTips AI Agent.

Selects the best LLM for each task type based on cost, quality, and availability.
Falls back gracefully if the primary brain is unavailable.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BrainDefinition:
    """Metadata about a single LLM brain."""

    name: str
    provider: str
    model: str
    best_for: List[str]
    cost_tier: str  # 'free', 'low', 'medium', 'high'
    speed_rating: int  # 1 (slowest) – 5 (fastest)
    context_window: int = 8192
    api_key: str = ""  # Used for dynamically-added custom brains


BRAINS: Dict[str, BrainDefinition] = {
    "copilot": BrainDefinition(
        name="copilot",
        provider="github_copilot",
        model="gpt-4o",
        best_for=["code_generation", "technical_tasks", "general"],
        cost_tier="free",
        speed_rating=4,
        context_window=128000,
    ),
    "openrouter_claude": BrainDefinition(
        name="openrouter_claude",
        provider="openrouter",
        model="anthropic/claude-3.5-sonnet",
        best_for=["content_writing", "seo_optimize", "create_content", "update_content"],
        cost_tier="medium",
        speed_rating=3,
        context_window=200000,
    ),
    "openrouter_gpt4": BrainDefinition(
        name="openrouter_gpt4",
        provider="openrouter",
        model="openai/gpt-4o",
        best_for=["analytics", "site_audit", "content_plan", "general"],
        cost_tier="medium",
        speed_rating=4,
        context_window=128000,
    ),
    "kimi": BrainDefinition(
        name="kimi",
        provider="kimi",
        model="moonshot-v1-128k",
        best_for=["long_context", "bulk_update", "content_plan"],
        cost_tier="low",
        speed_rating=3,
        context_window=128000,
    ),
    "nvidia_nemotron": BrainDefinition(
        name="nvidia_nemotron",
        provider="nvidia",
        model="nvidia/llama-3.1-nemotron-70b-instruct",
        best_for=["seo_optimize", "keyword_research", "technical_tasks"],
        cost_tier="low",
        speed_rating=4,
        context_window=131072,
    ),
    "nvidia_kimi": BrainDefinition(
        name="nvidia_kimi",
        provider="nvidia",
        model="moonshotai/kimi-k2.5",
        best_for=["create_content", "long_context", "content_plan"],
        cost_tier="low",
        speed_rating=4,
        context_window=131072,
    ),
    "local_ollama": BrainDefinition(
        name="local_ollama",
        provider="ollama",
        model="llama3.2",
        best_for=["quick_tasks", "summarize", "classify"],
        cost_tier="free",
        speed_rating=2,
        context_window=8192,
    ),
}

# Priority order when routing by task type (first match wins)
TASK_ROUTING: Dict[str, List[str]] = {
    "create_content": ["openrouter_claude", "nvidia_kimi", "copilot", "openrouter_gpt4", "kimi", "local_ollama"],
    "update_content": ["openrouter_claude", "copilot", "openrouter_gpt4", "kimi", "local_ollama"],
    "seo_optimize": ["nvidia_nemotron", "openrouter_claude", "openrouter_gpt4", "copilot", "local_ollama"],
    "design_update": ["copilot", "openrouter_gpt4", "openrouter_claude", "local_ollama"],
    "design_analysis": ["copilot", "openrouter_gpt4", "openrouter_claude", "local_ollama"],
    "create_page": ["openrouter_claude", "copilot", "openrouter_gpt4", "local_ollama"],
    "site_audit": ["openrouter_gpt4", "copilot", "openrouter_claude", "local_ollama"],
    "content_plan": ["nvidia_kimi", "kimi", "openrouter_claude", "openrouter_gpt4", "copilot", "local_ollama"],
    "analytics": ["openrouter_gpt4", "copilot", "openrouter_claude", "local_ollama"],
    "bulk_update": ["kimi", "openrouter_claude", "openrouter_gpt4", "copilot", "local_ollama"],
    "keyword_research": ["nvidia_nemotron", "openrouter_claude", "copilot", "local_ollama"],
    "long_context": ["nvidia_kimi", "kimi", "openrouter_claude", "copilot", "local_ollama"],
    "deep_crawl": ["copilot", "openrouter_gpt4", "openrouter_claude", "local_ollama"],
    "auto_link": ["openrouter_claude", "copilot", "openrouter_gpt4", "local_ollama"],
    "auto_fix": ["copilot", "openrouter_claude", "openrouter_gpt4", "local_ollama"],
    "general": ["copilot", "openrouter_gpt4", "openrouter_claude", "local_ollama"],
}

# Pre-configured model presets that can be added with one call
PRESET_MODELS: Dict[str, Dict[str, Any]] = {
    # NVIDIA-hosted models (all use the same NVIDIA API key)
    "nvidia_kimi_k2.5": {
        "provider": "nvidia", "model": "moonshotai/kimi-k2.5",
        "best_for": ["create_content", "long_context"], "cost_tier": "low",
        "speed_rating": 4, "context_window": 131072,
    },
    "nvidia_deepseek_r1": {
        "provider": "nvidia", "model": "deepseek-ai/deepseek-r1",
        "best_for": ["code_generation", "technical_tasks"], "cost_tier": "low",
        "speed_rating": 3, "context_window": 131072,
    },
    "nvidia_llama_3.3": {
        "provider": "nvidia", "model": "meta/llama-3.3-70b-instruct",
        "best_for": ["general", "create_content"], "cost_tier": "low",
        "speed_rating": 4, "context_window": 131072,
    },
    "nvidia_gemma_27b": {
        "provider": "nvidia", "model": "google/gemma-2-27b-it",
        "best_for": ["summarize", "classify"], "cost_tier": "low",
        "speed_rating": 4, "context_window": 8192,
    },
    "nvidia_mistral_large": {
        "provider": "nvidia", "model": "mistralai/mistral-large-2-instruct",
        "best_for": ["create_content", "seo_optimize"], "cost_tier": "low",
        "speed_rating": 4, "context_window": 131072,
    },
    "nvidia_phi3": {
        "provider": "nvidia", "model": "microsoft/phi-3-medium-128k-instruct",
        "best_for": ["quick_tasks", "classify"], "cost_tier": "low",
        "speed_rating": 5, "context_window": 128000,
    },
    # GitHub Models (Student Pack)
    "github_gpt4o": {
        "provider": "github_models", "model": "gpt-4o",
        "best_for": ["general", "create_content", "analytics"], "cost_tier": "free",
        "speed_rating": 4, "context_window": 128000,
    },
    "github_gpt4o_mini": {
        "provider": "github_models", "model": "gpt-4o-mini",
        "best_for": ["quick_tasks", "classify", "summarize"], "cost_tier": "free",
        "speed_rating": 5, "context_window": 128000,
    },
    "github_o1_mini": {
        "provider": "github_models", "model": "o1-mini",
        "best_for": ["code_generation", "technical_tasks"], "cost_tier": "free",
        "speed_rating": 3, "context_window": 128000,
    },
    "github_llama_405b": {
        "provider": "github_models", "model": "Meta-Llama-3.1-405B-Instruct",
        "best_for": ["create_content", "long_context"], "cost_tier": "free",
        "speed_rating": 3, "context_window": 128000,
    },
    # OpenRouter models
    "openrouter_claude_sonnet_4": {
        "provider": "openrouter", "model": "anthropic/claude-sonnet-4-20250514",
        "best_for": ["create_content", "seo_optimize", "update_content"], "cost_tier": "medium",
        "speed_rating": 3, "context_window": 200000,
    },
    "openrouter_gemini_pro": {
        "provider": "openrouter", "model": "google/gemini-2.0-flash-exp:free",
        "best_for": ["general", "quick_tasks"], "cost_tier": "free",
        "speed_rating": 5, "context_window": 1000000,
    },
    "openrouter_deepseek_chat": {
        "provider": "openrouter", "model": "deepseek/deepseek-chat",
        "best_for": ["code_generation", "technical_tasks"], "cost_tier": "low",
        "speed_rating": 4, "context_window": 64000,
    },
}


class BrainRouter:
    """Intelligent multi-LLM router.

    Selects the most appropriate LLM client for a given task and transparently
    falls back to the next best option on failure.
    """

    def __init__(self, config: Any = None) -> None:
        """Initialise the brain router with optional AppConfig.

        Args:
            config: AppConfig instance (used to initialise LLM clients lazily).
        """
        self.config = config
        self._clients: Dict[str, Any] = {}
        self._available_brains: List[str] = list(BRAINS.keys())
        # Runtime registry merging built-in and custom brains
        self._brains: Dict[str, BrainDefinition] = dict(BRAINS)
        # Load persisted custom brains if memory is available
        self._memory: Optional[Any] = None
        # When set, route() always returns this brain (dashboard override)
        self.forced_brain: Optional[str] = None
        self._load_custom_brains()

    def _get_memory(self) -> Optional[Any]:
        """Return the memory store, initialising it lazily."""
        if self._memory is None and self.config is not None:
            try:
                from agent.core.memory import AgentMemory
                db_path = getattr(self.config.agent, "custom_brains_db_path", "data/memory.db")
                self._memory = AgentMemory(db_path=db_path)
            except Exception:  # noqa: BLE001
                pass
        return self._memory

    def _load_custom_brains(self) -> None:
        """Load persisted custom brains from the database into the runtime registry."""
        memory = self._get_memory()
        if memory is None:
            return
        try:
            for brain_dict in memory.load_custom_brains():
                self._register_brain_from_dict(brain_dict)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load custom brains: %s", exc)

    def _register_brain_from_dict(self, brain_dict: Dict[str, Any]) -> None:
        """Register a BrainDefinition from a dict (used for custom brains)."""
        brain = BrainDefinition(
            name=brain_dict["name"],
            provider=brain_dict["provider"],
            model=brain_dict["model"],
            best_for=brain_dict.get("best_for", []),
            cost_tier=brain_dict.get("cost_tier", "medium"),
            speed_rating=int(brain_dict.get("speed_rating", 3)),
            context_window=int(brain_dict.get("context_window", 8192)),
            api_key=brain_dict.get("api_key", ""),
        )
        self._brains[brain.name] = brain
        if brain.name not in self._available_brains:
            self._available_brains.append(brain.name)

    # ------------------------------------------------------------------
    # Client lazy-loading
    # ------------------------------------------------------------------

    def _get_client(self, brain_name: str) -> Any:
        """Return (and cache) the API client for a brain.

        Args:
            brain_name: Key in _brains dict.

        Returns:
            API client instance.

        Raises:
            ValueError: If brain_name is unknown.
        """
        if brain_name in self._clients:
            return self._clients[brain_name]

        brain = self._brains[brain_name]

        if brain.provider == "github_copilot":
            from agent.integrations.copilot_client import CopilotClient
            client = CopilotClient(
                token=brain.api_key or (self.config.llm.github_copilot_token if self.config else "")
            )
        elif brain.provider == "openrouter":
            from agent.integrations.openrouter_client import OpenRouterClient
            client = OpenRouterClient(
                api_key=brain.api_key or (self.config.llm.openrouter_api_key if self.config else "")
            )
        elif brain.provider == "kimi":
            from agent.integrations.kimi_client import KimiClient
            client = KimiClient(
                api_key=brain.api_key or (self.config.llm.kimi_api_key if self.config else "")
            )
        elif brain.provider == "nvidia":
            from agent.integrations.nvidia_client import NvidiaClient
            client = NvidiaClient(
                api_key=brain.api_key or (self.config.llm.nvidia_api_key if self.config else "")
            )
        elif brain.provider == "github_models":
            from agent.integrations.github_models_client import GitHubModelsClient
            client = GitHubModelsClient(
                token=brain.api_key or (
                    self.config.llm.github_token if self.config else os.environ.get("GITHUB_TOKEN", "")
                )
            )
        elif brain.provider == "ollama":
            from agent.integrations.ollama_client import OllamaClient
            client = OllamaClient(
                host=brain.api_key or (self.config.llm.ollama_host if self.config else "http://localhost:11434")
            )
        elif brain.provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=brain.api_key)
        else:
            # Generic OpenAI-compatible provider
            from openai import OpenAI
            client = OpenAI(api_key=brain.api_key, base_url=brain.provider)

        self._clients[brain_name] = client
        return client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(
        self,
        task_type: str,
        content_length: int = 0,
        priority: str = "balanced",
    ) -> str:
        """Select the best available brain for a task.

        Args:
            task_type: Type of task (must be a key in TASK_ROUTING or 'general').
            content_length: Approximate token count of the content (used for
                context-window filtering).
            priority: 'cost' (prefer free/low), 'speed' (prefer fast),
                      'quality' (prefer best), or 'balanced'.

        Returns:
            Brain name string.
        """
        # If a brain is forced (e.g. via dashboard selector), always use it
        if self.forced_brain and self.forced_brain in self._brains:
            return self.forced_brain

        candidates = TASK_ROUTING.get(task_type, TASK_ROUTING["general"])

        # Include custom brains that are specifically good for this task_type
        # (built-in routing table takes precedence; custom brains are appended)
        extra = [
            name for name, b in self._brains.items()
            if name not in candidates and task_type in b.best_for
        ]
        candidates = list(candidates) + extra

        # Filter by context window
        if content_length > 0:
            candidates = [
                b for b in candidates
                if self._brains[b].context_window >= content_length
            ] or candidates  # fall back to full list if none qualify

        # Filter to available brains only
        candidates = [b for b in candidates if b in self._available_brains] or list(
            self._brains.keys()
        )

        if priority == "cost":
            tier_order = {"free": 0, "low": 1, "medium": 2, "high": 3}
            candidates = sorted(
                candidates, key=lambda b: tier_order.get(self._brains[b].cost_tier, 99)
            )
        elif priority == "speed":
            candidates = sorted(
                candidates, key=lambda b: self._brains[b].speed_rating, reverse=True
            )

        return candidates[0]

    def generate(
        self,
        brain_name: str,
        prompt: str,
        system_prompt: str = "",
        images: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:
        """Call the selected LLM and return the text response.

        Falls back to ALL other available brains on failure.

        Args:
            brain_name: Brain to use (from _brains keys).
            prompt: User message.
            system_prompt: Optional system/persona message.
            images: Optional list of image data-URIs or URLs to send
                    as vision input (base64 data-URIs preferred).
            **kwargs: Extra parameters forwarded to the client (temperature, etc.).

        Returns:
            LLM response text.

        Raises:
            RuntimeError: If all brains fail.
        """
        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Build user message — multimodal if images attached
        if images:
            content_parts: List[Dict[str, Any]] = [
                {"type": "text", "text": prompt}
            ]
            for img in images:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": img},
                })
            messages.append({"role": "user", "content": content_parts})
        else:
            messages.append({"role": "user", "content": prompt})

        fallback_order = [brain_name] + [
            b for b in self._available_brains if b != brain_name
        ]

        last_exc: Optional[Exception] = None
        for candidate in fallback_order:
            start_time = time.time()
            try:
                brain = self._brains[candidate]
                client = self._get_client(candidate)
                logger.debug("Generating with brain=%s model=%s", candidate, brain.model)

                if brain.provider == "openrouter":
                    result = client.chat_completion(
                        model=brain.model, messages=messages, **kwargs
                    )
                elif brain.provider == "github_copilot":
                    result = client.chat_completion(
                        model=brain.model, messages=messages, **kwargs
                    )
                elif brain.provider == "kimi":
                    result = client.chat_completion(messages=messages, **kwargs)
                elif brain.provider in ("nvidia", "github_models"):
                    result = client.chat_completion(
                        model=brain.model, messages=messages, **kwargs
                    )
                elif brain.provider == "ollama":
                    result = client.chat_completion(
                        model=brain.model, messages=messages, **kwargs
                    )
                else:
                    # Generic OpenAI-compatible client (openai, custom)
                    response = client.chat.completions.create(
                        model=brain.model, messages=messages, **kwargs
                    )
                    result = response.choices[0].message.content or ""

                elapsed = time.time() - start_time
                self._log_usage(candidate, success=True, response_time=elapsed)
                return result
            except Exception as exc:  # noqa: BLE001
                elapsed = time.time() - start_time
                self._log_usage(candidate, success=False, response_time=elapsed)
                logger.warning("Brain %s failed: %s", candidate, exc)
                last_exc = exc

        raise RuntimeError(
            f"All brains failed. Last error: {last_exc}"
        )

    def _log_usage(
        self, brain_name: str, success: bool, response_time: float
    ) -> None:
        """Log brain usage to memory if available."""
        memory = self._get_memory()
        if memory is not None:
            try:
                memory.log_brain_usage(brain_name, success=success, response_time=response_time)
            except Exception:  # noqa: BLE001
                pass

    def mark_unavailable(self, brain_name: str) -> None:
        """Temporarily mark a brain as unavailable for routing.

        Args:
            brain_name: The brain to exclude from routing.
        """
        if brain_name in self._available_brains:
            self._available_brains.remove(brain_name)
            logger.info("Brain %s marked unavailable", brain_name)

    def mark_available(self, brain_name: str) -> None:
        """Re-enable a previously disabled brain.

        Args:
            brain_name: The brain to re-add to routing.
        """
        if brain_name not in self._available_brains and brain_name in self._brains:
            self._available_brains.append(brain_name)
            logger.info("Brain %s marked available", brain_name)

    # ------------------------------------------------------------------
    # Dynamic brain management
    # ------------------------------------------------------------------

    def add_brain(
        self,
        name: str,
        provider: str,
        model: str,
        api_key: str = "",
        best_for: Optional[List[str]] = None,
        cost_tier: str = "medium",
        speed_rating: int = 3,
        context_window: int = 8192,
    ) -> None:
        """Add a new LLM brain at runtime and persist it.

        Args:
            name: Unique identifier for this brain.
            provider: Provider type (openrouter/ollama/nvidia/kimi/openai/custom URL).
            model: Model identifier string.
            api_key: API key or host URL for the provider.
            best_for: Task types this brain excels at.
            cost_tier: One of 'free', 'low', 'medium', 'high'.
            speed_rating: Integer 1–5 (5 fastest).
            context_window: Maximum context length in tokens.
        """
        brain_dict: Dict[str, Any] = {
            "name": name,
            "provider": provider,
            "model": model,
            "api_key": api_key,
            "best_for": best_for or [],
            "cost_tier": cost_tier,
            "speed_rating": speed_rating,
            "context_window": context_window,
        }
        self._register_brain_from_dict(brain_dict)
        # Remove cached client so it is re-created with new api_key
        self._clients.pop(name, None)
        memory = self._get_memory()
        if memory is not None:
            memory.save_custom_brain(brain_dict)
        logger.info("Brain %s added (provider=%s, model=%s)", name, provider, model)

    def remove_brain(self, name: str) -> None:
        """Remove a brain from the router.

        Built-in brains are removed from the runtime registry but not from the
        BRAINS constant. Custom brains are also deleted from the database.

        Args:
            name: Brain name to remove.
        """
        self._brains.pop(name, None)
        self._clients.pop(name, None)
        if name in self._available_brains:
            self._available_brains.remove(name)
        memory = self._get_memory()
        if memory is not None:
            try:
                memory.delete_custom_brain(name)
            except Exception:  # noqa: BLE001
                pass
        logger.info("Brain %s removed", name)

    def update_brain_api_key(self, name: str, new_api_key: str) -> None:
        """Update the API key for an existing brain.

        Args:
            name: Brain name.
            new_api_key: New API key or host URL.
        """
        if name not in self._brains:
            raise ValueError(f"Unknown brain: {name}")
        self._brains[name].api_key = new_api_key
        # Invalidate cached client so it is re-created with new key
        self._clients.pop(name, None)
        memory = self._get_memory()
        if memory is not None:
            brain = self._brains[name]
            memory.save_custom_brain({
                "name": brain.name,
                "provider": brain.provider,
                "model": brain.model,
                "api_key": new_api_key,
                "best_for": brain.best_for,
                "cost_tier": brain.cost_tier,
                "speed_rating": brain.speed_rating,
                "context_window": brain.context_window,
            })
        logger.info("Brain %s API key updated", name)

    def list_brains(self) -> List[Dict[str, Any]]:
        """Return all registered brains with their status.

        Returns:
            List of dicts with: name, provider, model, cost_tier, speed_rating,
            context_window, best_for, available.
        """
        return [
            {
                "name": b.name,
                "provider": b.provider,
                "model": b.model,
                "cost_tier": b.cost_tier,
                "speed_rating": b.speed_rating,
                "context_window": b.context_window,
                "best_for": b.best_for,
                "available": b.name in self._available_brains,
                "api_key_set": bool(b.api_key),
            }
            for b in self._brains.values()
        ]

    def clear_client_cache(self) -> None:
        """Invalidate all cached API clients.

        Call this after updating API keys in environment variables so that
        clients are re-created with the new credentials on next use.
        """
        self._clients.clear()
        logger.debug("BrainRouter client cache cleared")

    def get_preset_models(self) -> Dict[str, Dict[str, Any]]:
        """Return all pre-configured model presets.

        Returns:
            Dict mapping preset_name -> preset metadata dict.
        """
        return dict(PRESET_MODELS)

    def add_preset(self, preset_name: str, api_key: str = "") -> None:
        """Add a preset model to the router with one call.

        For NVIDIA-hosted models the existing NVIDIA API key is used (or the
        provided api_key).  For github_models presets the GITHUB_TOKEN is used.
        For openrouter presets the existing OpenRouter key is used.

        Args:
            preset_name: Key from PRESET_MODELS dict.
            api_key: Optional override API key/token.

        Raises:
            ValueError: If preset_name is not found in PRESET_MODELS.
        """
        if preset_name not in PRESET_MODELS:
            raise ValueError(
                f"Unknown preset '{preset_name}'. "
                f"Available presets: {list(PRESET_MODELS.keys())}"
            )
        preset = PRESET_MODELS[preset_name]
        provider = preset["provider"]

        # Resolve API key from config/env when not explicitly provided
        if not api_key:
            if provider == "nvidia":
                api_key = (
                    self.config.llm.nvidia_api_key
                    if self.config
                    else os.environ.get("NVIDIA_API_KEY", "")
                )
            elif provider == "github_models":
                api_key = (
                    self.config.llm.github_token
                    if self.config
                    else os.environ.get("GITHUB_TOKEN", "")
                )
            elif provider == "openrouter":
                api_key = (
                    self.config.llm.openrouter_api_key
                    if self.config
                    else os.environ.get("OPENROUTER_API_KEY", "")
                )

        self.add_brain(
            name=preset_name,
            provider=provider,
            model=preset["model"],
            api_key=api_key,
            best_for=preset.get("best_for", []),
            cost_tier=preset.get("cost_tier", "medium"),
            speed_rating=int(preset.get("speed_rating", 3)),
            context_window=int(preset.get("context_window", 8192)),
        )

    def test_brain(self, name: str) -> bool:
        """Send a simple test prompt to verify a brain works.

        Args:
            name: Brain name to test.

        Returns:
            True if the brain responds successfully, False otherwise.
        """
        if name not in self._brains:
            return False
        try:
            response = self.generate(
                brain_name=name,
                prompt="Reply with exactly: OK",
                system_prompt="You are a test assistant.",
            )
            return bool(response and len(response.strip()) > 0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Brain %s test failed: %s", name, exc)
            return False

    def get_brain_stats(self) -> Dict[str, Any]:
        """Return per-brain usage statistics.

        Returns:
            Dict mapping brain_name -> stats dict.
        """
        memory = self._get_memory()
        if memory is None:
            return {}
        try:
            return memory.get_brain_stats()
        except Exception:  # noqa: BLE001
            return {}

    def sync_copilot_brains(self, github_token: str) -> List[str]:
        """Fetch all Copilot models from the API and register each as a brain.

        This mirrors the VS Code model picker — every model available to your
        Copilot subscription appears as a selectable brain.

        Args:
            github_token: GitHub OAuth token stored in .env.

        Returns:
            List of brain names that were registered.
        """
        from agent.integrations.copilot_auth import list_copilot_models

        category_task_map: Dict[str, List[str]] = {
            "powerful":   ["create_content", "seo_optimize", "site_audit", "content_plan"],
            "versatile":  ["create_content", "update_content", "general", "analytics"],
            "lightweight": ["quick_tasks", "classify", "summarize", "keyword_research"],
        }

        models = list_copilot_models(github_token)
        registered: List[str] = []

        for m in models:
            brain_name = f"copilot_{m['id'].replace('.', '_').replace('-', '_')}"
            best_for = category_task_map.get(m["category"], ["general"])

            # Resolve API key from config/env
            api_key = (
                self.config.llm.github_copilot_token
                if self.config else os.environ.get("GITHUB_COPILOT_TOKEN", "")
            )

            self.add_brain(
                name=brain_name,
                provider="github_copilot",
                model=m["id"],
                api_key=api_key,
                best_for=best_for,
                cost_tier="free",
                speed_rating=4 if m["category"] == "lightweight" else 3,
                context_window=m["context_window"],
            )
            registered.append(brain_name)

        logger.info("Synced %d Copilot models as brains", len(registered))
        return registered
