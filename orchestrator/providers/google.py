"""Google (Gemini) provider."""

from __future__ import annotations

import re

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

# Delays longer than this are treated as daily-quota exhaustion — no retry.
_MAX_RETRY_DELAY: float = 60.0


def _extract_gemini_delay(exc: Exception) -> float | None:
    """Extract the retryDelay (seconds) from a Gemini 429 error, or return None.

    Tries structured access on the exception first (``exc.details``), then
    falls back to a regex search on the string representation.
    """
    # Structured access: google-genai errors expose a ``details`` list whose
    # entries may contain a google.rpc.RetryInfo entry with a ``retryDelay`` field.
    try:
        for detail in exc.details:  # type: ignore[attr-defined]
            if "RetryInfo" in detail.get("@type", ""):
                raw = detail.get("retryDelay", "")
                if raw:
                    return float(re.sub(r"[^0-9.]", "", raw))
    except (AttributeError, TypeError, ValueError):
        pass

    # Fallback: parse the string representation of the error.
    # The message typically contains: 'retryDelay': '36s' or '36.471s'
    match = re.search(r"'retryDelay':\s*'([0-9.]+)s'", str(exc))
    if match:
        return float(match.group(1))

    return None


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

        return await call_with_retry(
            _do,
            retryable=_RETRYABLE,
            delay_extractor=_extract_gemini_delay,
            max_retry_delay=_MAX_RETRY_DELAY,
        )
