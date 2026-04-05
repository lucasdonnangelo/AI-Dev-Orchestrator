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
) -> T:
    """Call async fn with exponential backoff on retryable exceptions.

    Args:
        fn: Zero-argument async callable to invoke.
        max_attempts: Total number of attempts before re-raising.
        base_delay: Initial delay in seconds (doubles each retry).
        max_delay: Upper bound for the delay between retries.
        retryable: Exception types that trigger a retry.

    Returns:
        The return value of fn on success.

    Raises:
        The last exception raised by fn after all attempts are exhausted.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except retryable as exc:
            if attempt == max_attempts:
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
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
