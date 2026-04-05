"""Retry helper with exponential backoff for async provider calls."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

_log = logging.getLogger(__name__)

T = TypeVar("T")


async def call_with_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
    retryable: tuple[type[Exception], ...] = (Exception,),
    delay_extractor: Callable[[Exception], float | None] | None = None,
    max_retry_delay: float = 60.0,
) -> T:
    """Call async fn with exponential backoff on retryable exceptions.

    Args:
        fn: Zero-argument async callable to invoke.
        max_attempts: Total number of attempts before re-raising.
        base_delay: Initial delay in seconds (doubles each retry).
        max_delay: Upper bound for the computed backoff delay.
        retryable: Exception types that trigger a retry.
        delay_extractor: Optional callable that receives the exception and
            returns a provider-specific retry delay in seconds, or None to
            fall back to the computed backoff. When the extracted delay
            exceeds *max_retry_delay*, the exception is re-raised immediately
            (signals a non-transient quota exhaustion).
        max_retry_delay: Ceiling for delays returned by *delay_extractor*.
            Delays above this value are treated as daily quota exhaustion
            and cause an immediate re-raise without further retries.

    Returns:
        The return value of fn on success.

    Raises:
        The last exception raised by fn after all attempts are exhausted,
        or immediately if the extracted retry delay exceeds max_retry_delay.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except retryable as exc:
            if attempt == max_attempts:
                raise

            # Determine how long to wait before the next attempt.
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)

            if delay_extractor is not None:
                extracted = delay_extractor(exc)
                if extracted is not None:
                    if extracted > max_retry_delay:
                        _log.warning(
                            "[!] Quota likely exhausted (API retryDelay=%.0fs > %.0fs limit)"
                            " — not retrying",
                            extracted,
                            max_retry_delay,
                        )
                        raise
                    delay = extracted

            _log.warning(
                "[!] API call failed (attempt %d/%d): %s — retrying in %.1fs",
                attempt,
                max_attempts,
                exc,
                delay,
            )
            await asyncio.sleep(delay)

    # Unreachable — satisfies type checker
    raise RuntimeError("call_with_retry: unreachable")
