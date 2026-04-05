"""Google (Gemini) provider."""

from __future__ import annotations

try:
    from google import genai as _genai
    from google.genai import types as _types
except ImportError:
    _genai = None  # type: ignore[assignment]
    _types = None  # type: ignore[assignment]

try:
    from google.genai import errors as _genai_errors

    _RETRYABLE: tuple[type[Exception], ...] = (
        _genai_errors.ServerError,   # 5xx — transient server-side failure
        _genai_errors.ClientError,   # includes 429 rate limit
    )
except (ImportError, AttributeError):
    _RETRYABLE = (Exception,)

from orchestrator.providers.base import BaseAgent
from orchestrator.providers.retry import call_with_retry

_MISSING_MSG = (
    "google-genai is not installed. "
    "Run: pip install 'google-genai>=1.0.0'"
)


class GeminiProvider(BaseAgent):
    """Calls the Google Gemini API via the google-genai SDK."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        if _genai is None:
            raise ImportError(_MISSING_MSG)
        self._client = _genai.Client(api_key=api_key)
        self._model = model

    async def call(self, prompt: str, system: str = "") -> str:
        async def _do() -> str:
            cfg = _types.GenerateContentConfig(system_instruction=system) if system else None
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=cfg,
            )
            return response.text

        return await call_with_retry(_do, retryable=_RETRYABLE)
