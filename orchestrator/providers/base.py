"""Abstract base class for all AI provider agents."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseAgent(ABC):
    """Common interface every provider must implement.

    Providers wrap a specific AI SDK (Anthropic, Google, OpenAI, etc.) and
    expose a single async ``call`` method so the rest of the orchestrator is
    provider-agnostic.
    """

    @abstractmethod
    async def call(self, prompt: str, system: str = "") -> str:
        """Send a prompt to the model and return the raw text response.

        Args:
            prompt: The user-turn content to send.
            system: Optional system prompt / instruction.

        Returns:
            The model's text response as a plain string.
        """
