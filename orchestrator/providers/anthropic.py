"""Anthropic (Claude) provider."""

from __future__ import annotations

import anthropic as _anthropic
from anthropic import AsyncAnthropic

from orchestrator.providers.base import BaseAgent
from orchestrator.providers.retry import call_with_retry

_RETRYABLE = (
    _anthropic.RateLimitError,
    _anthropic.APITimeoutError,
    _anthropic.InternalServerError,
)


class ClaudeProvider(BaseAgent):
    """Calls the Anthropic Messages API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def call(self, prompt: str, system: str = "") -> str:
        async def _do() -> str:
            kwargs: dict = {
                "model": self._model,
                "max_tokens": 2048,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                kwargs["system"] = system
            response = await self._client.messages.create(**kwargs)
            return response.content[0].text

        return await call_with_retry(_do, retryable=_RETRYABLE)
