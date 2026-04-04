"""Provider package — factory + re-exports."""

from __future__ import annotations

from typing import TYPE_CHECKING

from orchestrator.providers.base import BaseAgent
from orchestrator.providers.anthropic import ClaudeProvider
from orchestrator.providers.google import GeminiProvider
from orchestrator.providers.openai import OpenAIProvider

if TYPE_CHECKING:
    from orchestrator.config import Config

__all__ = [
    "BaseAgent",
    "ClaudeProvider",
    "GeminiProvider",
    "OpenAIProvider",
    "make_provider",
]


def make_provider(provider_name: str, config: Config) -> BaseAgent:
    """Instantiate the correct provider for the given name.

    Args:
        provider_name: One of ``"anthropic"``, ``"google"``, ``"openai"``.
        config: Resolved orchestrator configuration (supplies API keys and models).

    Returns:
        A ready-to-use :class:`BaseAgent` instance.

    Raises:
        ValueError: If the provider name is unknown.
        ImportError: If the required SDK for that provider is not installed.
    """
    name = provider_name.lower().strip()
    if name == "anthropic":
        return ClaudeProvider(api_key=config.api_key, model=config.model)
    if name == "google":
        return GeminiProvider(api_key=config.google_api_key, model=config.google_model)
    if name == "openai":
        return OpenAIProvider(api_key=config.openai_api_key, model=config.openai_model)
    raise ValueError(
        f"Unknown provider: {provider_name!r}. "
        "Valid options: anthropic, google, openai"
    )
