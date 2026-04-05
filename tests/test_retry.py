"""Unit tests for orchestrator/providers/retry.py."""

from __future__ import annotations

import pytest

from orchestrator.providers.retry import call_with_retry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _Transient(Exception):
    """Simulates a transient API error (rate limit, timeout, etc.)."""


class _Fatal(Exception):
    """Simulates a non-retryable error."""


def _make_flaky(fail_times: int, exc: Exception | None = None):
    """Returns an async callable that fails `fail_times` times then succeeds."""
    calls = {"n": 0}
    error = exc or _Transient("flaky error")

    async def _fn() -> str:
        calls["n"] += 1
        if calls["n"] <= fail_times:
            raise error
        return "ok"

    return _fn, calls


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

class TestCallWithRetrySuccess:
    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self):
        async def _fn() -> str:
            return "result"

        result = await call_with_retry(_fn, retryable=(_Transient,))
        assert result == "result"

    @pytest.mark.asyncio
    async def test_succeeds_after_one_failure(self):
        fn, calls = _make_flaky(fail_times=1)
        result = await call_with_retry(fn, retryable=(_Transient,), base_delay=0)
        assert result == "ok"
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_succeeds_after_two_failures(self):
        fn, calls = _make_flaky(fail_times=2)
        result = await call_with_retry(fn, max_attempts=3, retryable=(_Transient,), base_delay=0)
        assert result == "ok"
        assert calls["n"] == 3


# ---------------------------------------------------------------------------
# Exhausted retries
# ---------------------------------------------------------------------------

class TestCallWithRetryExhausted:
    @pytest.mark.asyncio
    async def test_raises_after_max_attempts(self):
        fn, calls = _make_flaky(fail_times=10)
        with pytest.raises(_Transient):
            await call_with_retry(fn, max_attempts=3, retryable=(_Transient,), base_delay=0)
        assert calls["n"] == 3

    @pytest.mark.asyncio
    async def test_max_attempts_one_raises_immediately(self):
        fn, calls = _make_flaky(fail_times=1)
        with pytest.raises(_Transient):
            await call_with_retry(fn, max_attempts=1, retryable=(_Transient,), base_delay=0)
        assert calls["n"] == 1


# ---------------------------------------------------------------------------
# Non-retryable exceptions pass through immediately
# ---------------------------------------------------------------------------

class TestCallWithRetryNonRetryable:
    @pytest.mark.asyncio
    async def test_non_retryable_raises_immediately(self):
        fn, calls = _make_flaky(fail_times=1, exc=_Fatal("fatal"))
        with pytest.raises(_Fatal):
            await call_with_retry(fn, max_attempts=3, retryable=(_Transient,), base_delay=0)
        # Only one attempt — no retry on _Fatal
        assert calls["n"] == 1


# ---------------------------------------------------------------------------
# Delay cap (max_delay)
# ---------------------------------------------------------------------------

class TestCallWithRetryDelays:
    @pytest.mark.asyncio
    async def test_delay_is_capped_at_max_delay(self, monkeypatch):
        """Ensure sleep is called with a value <= max_delay."""
        slept: list[float] = []

        async def _fake_sleep(seconds: float) -> None:
            slept.append(seconds)

        monkeypatch.setattr("orchestrator.providers.retry.asyncio.sleep", _fake_sleep)

        fn, _ = _make_flaky(fail_times=2)
        await call_with_retry(
            fn,
            max_attempts=3,
            retryable=(_Transient,),
            base_delay=100.0,
            max_delay=5.0,
        )

        assert all(s <= 5.0 for s in slept), f"Sleep exceeded max_delay: {slept}"

    @pytest.mark.asyncio
    async def test_backoff_doubles_each_attempt(self, monkeypatch):
        slept: list[float] = []

        async def _fake_sleep(seconds: float) -> None:
            slept.append(seconds)

        monkeypatch.setattr("orchestrator.providers.retry.asyncio.sleep", _fake_sleep)

        fn, _ = _make_flaky(fail_times=3)
        await call_with_retry(
            fn,
            max_attempts=4,
            retryable=(_Transient,),
            base_delay=1.0,
            max_delay=999.0,
        )

        assert slept == [1.0, 2.0, 4.0]
