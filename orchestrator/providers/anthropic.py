"""Anthropic (Claude) provider."""

from __future__ import annotations

import json

import anthropic as _anthropic
from anthropic import AsyncAnthropic

from orchestrator.providers.base import BaseAgent
from orchestrator.providers.retry import call_with_retry


class _EmptyResponseError(Exception):
    """Raised when the API returns HTTP 200 with no content blocks."""


_RETRYABLE = (
    _anthropic.RateLimitError,
    _anthropic.APITimeoutError,
    _anthropic.InternalServerError,
    # HTTP 200 with empty body: SDK raises JSONDecodeError when parsing it.
    json.JSONDecodeError,
    # HTTP 200 parsed successfully but content list is empty.
    _EmptyResponseError,
)


class ClaudeProvider(BaseAgent):
    """Calls the Anthropic Messages API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def call(self, prompt: str, system: str = "", max_tokens: int = 2048) -> str:
        async def _do() -> str:
            kwargs: dict = {
                "model": self._model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                kwargs["system"] = system
            response = await self._client.messages.create(**kwargs)
            if not response.content:
                raise _EmptyResponseError("API returned empty content block list")
            return response.content[0].text

        return await call_with_retry(_do, retryable=_RETRYABLE)
