"""Unit tests for orchestrator/providers/retry.py."""

from __future__ import annotations

import pytest

from orchestrator.providers.retry import call_with_retry
from orchestrator.providers.google import _extract_gemini_delay


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


# ---------------------------------------------------------------------------
# delay_extractor — provider-supplied delay override
# ---------------------------------------------------------------------------

class TestDelayExtractor:
    @pytest.mark.asyncio
    async def test_extracted_delay_overrides_backoff(self, monkeypatch):
        """delay_extractor return value is used instead of computed backoff."""
        slept: list[float] = []

        async def _fake_sleep(seconds: float) -> None:
            slept.append(seconds)

        monkeypatch.setattr("orchestrator.providers.retry.asyncio.sleep", _fake_sleep)

        fn, _ = _make_flaky(fail_times=1)
        await call_with_retry(
            fn,
            max_attempts=3,
            retryable=(_Transient,),
            base_delay=99.0,
            delay_extractor=lambda exc: 7.5,
        )

        assert slept == [7.5]

    @pytest.mark.asyncio
    async def test_extracted_delay_above_max_raises_immediately(self):
        """delay > max_retry_delay means quota exhausted — raise without retry."""
        fn, calls = _make_flaky(fail_times=10)

        with pytest.raises(_Transient):
            await call_with_retry(
                fn,
                max_attempts=5,
                retryable=(_Transient,),
                base_delay=0,
                delay_extractor=lambda exc: 120.0,  # > default max_retry_delay=60
                max_retry_delay=60.0,
            )

        # Must have given up after just 1 attempt (no retries)
        assert calls["n"] == 1

    @pytest.mark.asyncio
    async def test_extractor_returning_none_falls_back_to_backoff(self, monkeypatch):
        """None from extractor falls through to normal backoff."""
        slept: list[float] = []

        async def _fake_sleep(seconds: float) -> None:
            slept.append(seconds)

        monkeypatch.setattr("orchestrator.providers.retry.asyncio.sleep", _fake_sleep)

        fn, _ = _make_flaky(fail_times=1)
        await call_with_retry(
            fn,
            max_attempts=3,
            retryable=(_Transient,),
            base_delay=5.0,
            max_delay=999.0,
            delay_extractor=lambda exc: None,
        )

        assert slept == [5.0]


# ---------------------------------------------------------------------------
# _extract_gemini_delay — Gemini retryDelay parser
# ---------------------------------------------------------------------------

class TestExtractGeminiDelay:
    def _make_exc(self, details=None, message="") -> Exception:
        """Build a fake exception that resembles a google.genai ClientError."""
        exc = Exception(message)
        if details is not None:
            exc.details = details  # type: ignore[attr-defined]
        return exc

    def test_extracts_from_structured_details(self):
        exc = self._make_exc(details=[
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "36s"},
        ])
        assert _extract_gemini_delay(exc) == 36.0

    def test_extracts_fractional_seconds_from_details(self):
        exc = self._make_exc(details=[
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "36.471s"},
        ])
        assert _extract_gemini_delay(exc) == pytest.approx(36.471, rel=1e-3)

    def test_falls_back_to_string_repr(self):
        exc = Exception("429 RESOURCE_EXHAUSTED. {'error': {'retryDelay': '49s'}}")
        result = _extract_gemini_delay(exc)
        assert result == 49.0

    def test_returns_none_when_no_delay_info(self):
        exc = Exception("Some generic error without delay info")
        assert _extract_gemini_delay(exc) is None

    def test_returns_none_when_details_has_no_retry_info(self):
        exc = self._make_exc(details=[
            {"@type": "type.googleapis.com/google.rpc.Help", "links": []},
        ])
        assert _extract_gemini_delay(exc) is None

    def test_handles_missing_details_attribute(self):
        exc = Exception("no details attr")
        assert _extract_gemini_delay(exc) is None
