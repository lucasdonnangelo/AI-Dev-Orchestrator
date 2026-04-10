"""Unit tests for orchestrator/events.py — EventBus and Event dataclass."""

from __future__ import annotations

import asyncio

import pytest

from orchestrator.events import Event, EventBus, EventType


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------

class TestEvent:
    def test_to_dict_contains_all_keys(self):
        event = Event(type=EventType.PLAN_STARTED, data={"task": "x"}, run_id="run-1")
        d = event.to_dict()
        assert set(d) == {"type", "run_id", "timestamp", "data"}

    def test_to_dict_type_is_string(self):
        event = Event(type=EventType.PLAN_STARTED, data={}, run_id="r")
        assert event.to_dict()["type"] == "plan_started"

    def test_timestamp_is_set(self):
        event = Event(type=EventType.CYCLE_APPROVED, data={}, run_id="r")
        assert event.timestamp  # non-empty string

    def test_data_preserved(self):
        event = Event(type=EventType.REVIEW_COMPLETED, data={"score": 9, "approved": True}, run_id="r")
        assert event.to_dict()["data"] == {"score": 9, "approved": True}


# ---------------------------------------------------------------------------
# EventType enum
# ---------------------------------------------------------------------------

class TestEventType:
    ALL_TYPES = [
        "plan_started", "plan_completed",
        "critic_round", "critic_consensus",
        "execute_started", "execute_completed",
        "review_started", "review_completed",
        "decision_started", "decision_completed",
        "cycle_approved", "cycle_escalated",
        "token_usage",
    ]

    def test_all_types_exist(self):
        values = {e.value for e in EventType}
        for t in self.ALL_TYPES:
            assert t in values, f"Missing EventType: {t}"

    def test_is_str_subclass(self):
        assert isinstance(EventType.PLAN_STARTED, str)


# ---------------------------------------------------------------------------
# EventBus — construction
# ---------------------------------------------------------------------------

class TestEventBusInit:
    def test_auto_run_id(self):
        bus = EventBus()
        assert bus.run_id  # non-empty

    def test_custom_run_id(self):
        bus = EventBus(run_id="my-run")
        assert bus.run_id == "my-run"

    def test_two_buses_have_different_run_ids(self):
        assert EventBus().run_id != EventBus().run_id

    def test_starts_with_no_subscribers(self):
        assert EventBus().subscriber_count == 0


# ---------------------------------------------------------------------------
# EventBus — subscribe / unsubscribe
# ---------------------------------------------------------------------------

class TestEventBusSubscription:
    def test_subscribe_increments_count(self):
        bus = EventBus()
        bus.subscribe(lambda e: None)
        assert bus.subscriber_count == 1

    def test_multiple_subscribers(self):
        bus = EventBus()
        bus.subscribe(lambda e: None)
        bus.subscribe(lambda e: None)
        assert bus.subscriber_count == 2

    def test_unsubscribe_decrements_count(self):
        bus = EventBus()
        cb = lambda e: None  # noqa: E731
        bus.subscribe(cb)
        bus.unsubscribe(cb)
        assert bus.subscriber_count == 0

    def test_unsubscribe_unknown_raises(self):
        bus = EventBus()
        with pytest.raises(ValueError):
            bus.unsubscribe(lambda e: None)


# ---------------------------------------------------------------------------
# EventBus — emit (sync callbacks)
# ---------------------------------------------------------------------------

class TestEventBusEmitSync:
    @pytest.mark.asyncio
    async def test_sync_callback_receives_event(self):
        received: list[Event] = []
        bus = EventBus()
        bus.subscribe(received.append)

        await bus.emit(EventType.PLAN_STARTED, {"task": "hello"})

        assert len(received) == 1
        assert received[0].type == EventType.PLAN_STARTED
        assert received[0].data == {"task": "hello"}
        assert received[0].run_id == bus.run_id

    @pytest.mark.asyncio
    async def test_multiple_callbacks_all_called(self):
        calls: list[str] = []
        bus = EventBus()
        bus.subscribe(lambda e: calls.append("a"))
        bus.subscribe(lambda e: calls.append("b"))

        await bus.emit(EventType.CYCLE_APPROVED)

        assert calls == ["a", "b"]

    @pytest.mark.asyncio
    async def test_emit_with_no_data_defaults_to_empty_dict(self):
        received: list[Event] = []
        bus = EventBus()
        bus.subscribe(received.append)

        await bus.emit(EventType.DECISION_STARTED)

        assert received[0].data == {}

    @pytest.mark.asyncio
    async def test_no_subscribers_does_not_raise(self):
        bus = EventBus()
        await bus.emit(EventType.PLAN_STARTED, {"task": "x"})  # should not raise


# ---------------------------------------------------------------------------
# EventBus — emit (async callbacks)
# ---------------------------------------------------------------------------

class TestEventBusEmitAsync:
    @pytest.mark.asyncio
    async def test_async_callback_is_awaited(self):
        received: list[Event] = []

        async def async_cb(event: Event) -> None:
            received.append(event)

        bus = EventBus()
        bus.subscribe(async_cb)
        await bus.emit(EventType.REVIEW_COMPLETED, {"score": 8})

        assert len(received) == 1
        assert received[0].data["score"] == 8

    @pytest.mark.asyncio
    async def test_mixed_sync_and_async_callbacks(self):
        calls: list[str] = []

        async def async_cb(e: Event) -> None:
            calls.append("async")

        bus = EventBus()
        bus.subscribe(lambda e: calls.append("sync"))
        bus.subscribe(async_cb)

        await bus.emit(EventType.EXECUTE_STARTED)

        assert calls == ["sync", "async"]


# ---------------------------------------------------------------------------
# EventBus — subscriber errors are swallowed
# ---------------------------------------------------------------------------

class TestEventBusErrorIsolation:
    @pytest.mark.asyncio
    async def test_failing_sync_subscriber_does_not_crash_emit(self):
        calls: list[str] = []

        def bad_cb(e: Event) -> None:
            raise RuntimeError("boom")

        bus = EventBus()
        bus.subscribe(bad_cb)
        bus.subscribe(lambda e: calls.append("ok"))

        await bus.emit(EventType.PLAN_STARTED)  # should not raise

        assert calls == ["ok"]

    @pytest.mark.asyncio
    async def test_failing_async_subscriber_does_not_crash_emit(self):
        calls: list[str] = []

        async def bad_async_cb(e: Event) -> None:
            raise ValueError("async boom")

        bus = EventBus()
        bus.subscribe(bad_async_cb)
        bus.subscribe(lambda e: calls.append("ok"))

        await bus.emit(EventType.CRITIC_ROUND)

        assert calls == ["ok"]


# ---------------------------------------------------------------------------
# EventBus — run_id is propagated to events
# ---------------------------------------------------------------------------

class TestEventBusRunId:
    @pytest.mark.asyncio
    async def test_emitted_events_carry_bus_run_id(self):
        received: list[Event] = []
        bus = EventBus(run_id="test-run-42")
        bus.subscribe(received.append)

        await bus.emit(EventType.CYCLE_APPROVED)

        assert received[0].run_id == "test-run-42"
