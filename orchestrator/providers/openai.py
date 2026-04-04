"""OpenAI (ChatGPT) provider."""

from __future__ import annotations

try:
    from openai import AsyncOpenAI as _AsyncOpenAI
except ImportError:
    _AsyncOpenAI = None  # type: ignore[assignment, misc]

from orchestrator.providers.base import BaseAgent

_MISSING_MSG = (
    "openai is not installed. "
    "Run: pip install 'openai>=1.50.0'"
)


class OpenAIProvider(BaseAgent):
    """Calls the OpenAI Chat Completions API."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        if _AsyncOpenAI is None:
            raise ImportError(_MISSING_MSG)
        self._client = _AsyncOpenAI(api_key=api_key)
        self._model = model

    async def call(self, prompt: str, system: str = "") -> str:
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
        )
        return response.choices[0].message.content or ""
