"""Unit tests for orchestrator/events.py — EventBus and Event dataclass."""

from __future__ import annotations

import asyncio

import pytest

from orchestrator.events import Event, EventBus, EventType, PauseController


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
    CYCLE_TYPES = [
        "plan_started", "plan_completed",
        "critic_round", "critic_consensus",
        "execute_started", "execute_completed",
        "review_started", "review_completed",
        "decision_started", "decision_completed",
        "cycle_approved", "cycle_escalated",
        "cycle_paused", "cycle_resumed",
        "token_usage",
    ]

    PLAN_RUNNER_TYPES = [
        "plan_loaded",
        "task_started",
        "task_done",
        "task_escalated",
        "task_skipped",
        "subphase_complete",
        "phase_complete",
        "plan_paused",
        "plan_resumed",
        "plan_complete",
        "plan_aborted",
    ]

    def test_all_cycle_types_exist(self):
        values = {e.value for e in EventType}
        for t in self.CYCLE_TYPES:
            assert t in values, f"Missing EventType: {t}"

    def test_all_plan_runner_types_exist(self):
        values = {e.value for e in EventType}
        for t in self.PLAN_RUNNER_TYPES:
            assert t in values, f"Missing plan runner EventType: {t}"

    def test_total_type_count(self):
        assert len(EventType) == len(self.CYCLE_TYPES) + len(self.PLAN_RUNNER_TYPES)

    def test_is_str_subclass(self):
        assert isinstance(EventType.PLAN_STARTED, str)

    def test_plan_runner_types_are_str(self):
        for et in [
            EventType.PLAN_LOADED, EventType.TASK_STARTED, EventType.TASK_DONE,
            EventType.TASK_ESCALATED, EventType.TASK_SKIPPED,
            EventType.SUBPHASE_COMPLETE, EventType.PHASE_COMPLETE,
            EventType.PLAN_PAUSED, EventType.PLAN_RESUMED,
            EventType.PLAN_COMPLETE, EventType.PLAN_ABORTED,
        ]:
            assert isinstance(et, str)


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


# ---------------------------------------------------------------------------
# PauseController
# ---------------------------------------------------------------------------

class TestPauseControllerInit:
    def test_starts_not_paused(self):
        ctrl = PauseController()
        assert not ctrl.is_paused

    def test_pause_sets_paused(self):
        ctrl = PauseController()
        ctrl.pause()
        assert ctrl.is_paused

    def test_resume_clears_paused(self):
        ctrl = PauseController()
        ctrl.pause()
        ctrl.resume()
        assert not ctrl.is_paused

    def test_pause_is_idempotent(self):
        ctrl = PauseController()
        ctrl.pause()
        ctrl.pause()  # second call should not raise
        assert ctrl.is_paused


class TestPauseControllerCheckPause:
    async def test_check_pause_returns_none_when_not_paused(self):
        ctrl = PauseController()
        result = await ctrl.check_pause()
        assert result is None

    async def test_check_pause_blocks_until_resume(self):
        ctrl = PauseController()
        ctrl.pause()

        async def resume_after_delay() -> None:
            await asyncio.sleep(0.05)
            ctrl.resume()

        asyncio.create_task(resume_after_delay())
        result = await ctrl.check_pause()
        assert result is None
        assert not ctrl.is_paused

    async def test_check_pause_returns_edited_plan(self):
        ctrl = PauseController()
        ctrl.pause()
        sentinel = object()

        async def resume_with_plan() -> None:
            await asyncio.sleep(0.05)
            ctrl.resume(edited_plan=sentinel)

        asyncio.create_task(resume_with_plan())
        result = await ctrl.check_pause()
        assert result is sentinel

    async def test_edited_plan_consumed_after_first_check(self):
        ctrl = PauseController()
        sentinel = object()
        ctrl.resume(edited_plan=sentinel)  # pre-load (not paused)

        # check_pause fast-path: not paused → returns None (plan is not consumed)
        result = await ctrl.check_pause()
        assert result is None  # fast path, plan not consumed

    async def test_edited_plan_consumed_only_once(self):
        ctrl = PauseController()
        ctrl.pause()
        sentinel = object()

        async def resume_task() -> None:
            await asyncio.sleep(0.01)
            ctrl.resume(edited_plan=sentinel)

        asyncio.create_task(resume_task())
        first = await ctrl.check_pause()
        assert first is sentinel

        # Calling again should return None (plan was consumed)
        second = await ctrl.check_pause()
        assert second is None

    async def test_timeout_raises_timeout_error(self):
        ctrl = PauseController()
        ctrl.PAUSE_TIMEOUT = 0.05  # override for test speed
        ctrl.pause()

        with pytest.raises(TimeoutError, match="30 minutes"):
            await ctrl.check_pause()

    async def test_after_timeout_controller_is_not_paused(self):
        ctrl = PauseController()
        ctrl.PAUSE_TIMEOUT = 0.05
        ctrl.pause()

        with pytest.raises(TimeoutError):
            await ctrl.check_pause()

        assert not ctrl.is_paused


# ---------------------------------------------------------------------------
# Plan runner event types — emit and payload round-trip
# ---------------------------------------------------------------------------

class TestPlanRunnerEvents:
    """Verify each new plan-runner EventType can be emitted and received."""

    @pytest.mark.asyncio
    async def test_plan_loaded_event(self):
        received: list[Event] = []
        bus = EventBus()
        bus.subscribe(received.append)

        payload = {
            "name": "MyProject",
            "phases": [{"id": "1", "name": "Setup", "task_count": 3}],
            "total_tasks": 3,
            "done_tasks": 0,
        }
        await bus.emit(EventType.PLAN_LOADED, payload)

        assert received[0].type == EventType.PLAN_LOADED
        assert received[0].data["name"] == "MyProject"
        assert received[0].data["total_tasks"] == 3

    @pytest.mark.asyncio
    async def test_task_started_event(self):
        received: list[Event] = []
        bus = EventBus()
        bus.subscribe(received.append)

        payload = {
            "task_id": "1.1.1",
            "description": "Create models",
            "phase_id": "1",
            "subphase_id": "1.1",
            "attempt": 1,
        }
        await bus.emit(EventType.TASK_STARTED, payload)

        assert received[0].type == EventType.TASK_STARTED
        assert received[0].data["task_id"] == "1.1.1"
        assert received[0].data["attempt"] == 1

    @pytest.mark.asyncio
    async def test_task_done_event(self):
        received: list[Event] = []
        bus = EventBus()
        bus.subscribe(received.append)

        payload = {"task_id": "1.1.1", "commit_hash": "abc1234", "score": 9, "duration_s": 42.0}
        await bus.emit(EventType.TASK_DONE, payload)

        assert received[0].type == EventType.TASK_DONE
        assert received[0].data["commit_hash"] == "abc1234"
        assert received[0].data["score"] == 9

    @pytest.mark.asyncio
    async def test_task_escalated_event(self):
        received: list[Event] = []
        bus = EventBus()
        bus.subscribe(received.append)

        await bus.emit(EventType.TASK_ESCALATED, {"task_id": "1.1.2", "reason": "max retries"})

        assert received[0].type == EventType.TASK_ESCALATED
        assert received[0].data["reason"] == "max retries"

    @pytest.mark.asyncio
    async def test_task_skipped_event(self):
        received: list[Event] = []
        bus = EventBus()
        bus.subscribe(received.append)

        await bus.emit(EventType.TASK_SKIPPED, {"task_id": "1.1.3"})

        assert received[0].type == EventType.TASK_SKIPPED
        assert received[0].data["task_id"] == "1.1.3"

    @pytest.mark.asyncio
    async def test_subphase_complete_event(self):
        received: list[Event] = []
        bus = EventBus()
        bus.subscribe(received.append)

        payload = {"subphase_id": "1.1", "done": 3, "escalated": 0, "skipped": 0, "duration_s": 120.5}
        await bus.emit(EventType.SUBPHASE_COMPLETE, payload)

        assert received[0].type == EventType.SUBPHASE_COMPLETE
        assert received[0].data["done"] == 3

    @pytest.mark.asyncio
    async def test_phase_complete_event(self):
        received: list[Event] = []
        bus = EventBus()
        bus.subscribe(received.append)

        payload = {"phase_id": "1", "done": 6, "escalated": 1, "skipped": 0, "duration_s": 300.0}
        await bus.emit(EventType.PHASE_COMPLETE, payload)

        assert received[0].type == EventType.PHASE_COMPLETE
        assert received[0].data["phase_id"] == "1"

    @pytest.mark.asyncio
    async def test_plan_paused_event(self):
        received: list[Event] = []
        bus = EventBus()
        bus.subscribe(received.append)

        payload = {"reason": "subphase", "context": {"done": 3, "commits": ["abc"]}}
        await bus.emit(EventType.PLAN_PAUSED, payload)

        assert received[0].type == EventType.PLAN_PAUSED
        assert received[0].data["reason"] == "subphase"

    @pytest.mark.asyncio
    async def test_plan_resumed_event(self):
        received: list[Event] = []
        bus = EventBus()
        bus.subscribe(received.append)

        await bus.emit(EventType.PLAN_RESUMED, {})

        assert received[0].type == EventType.PLAN_RESUMED
        assert received[0].data == {}

    @pytest.mark.asyncio
    async def test_plan_complete_event(self):
        received: list[Event] = []
        bus = EventBus()
        bus.subscribe(received.append)

        payload = {"total": 10, "done": 9, "escalated": 1, "skipped": 0, "duration_s": 600.0}
        await bus.emit(EventType.PLAN_COMPLETE, payload)

        assert received[0].type == EventType.PLAN_COMPLETE
        assert received[0].data["total"] == 10

    @pytest.mark.asyncio
    async def test_plan_aborted_event(self):
        received: list[Event] = []
        bus = EventBus()
        bus.subscribe(received.append)

        await bus.emit(EventType.PLAN_ABORTED, {"reason": "user cancelled"})

        assert received[0].type == EventType.PLAN_ABORTED
        assert received[0].data["reason"] == "user cancelled"

    @pytest.mark.asyncio
    async def test_plan_runner_events_carry_run_id(self):
        received: list[Event] = []
        bus = EventBus(run_id="plan-run-99")
        bus.subscribe(received.append)

        for et in [
            EventType.PLAN_LOADED, EventType.TASK_STARTED, EventType.TASK_DONE,
            EventType.TASK_ESCALATED, EventType.TASK_SKIPPED,
            EventType.SUBPHASE_COMPLETE, EventType.PHASE_COMPLETE,
            EventType.PLAN_PAUSED, EventType.PLAN_RESUMED,
            EventType.PLAN_COMPLETE, EventType.PLAN_ABORTED,
        ]:
            await bus.emit(et, {})

        assert all(e.run_id == "plan-run-99" for e in received)
        assert len(received) == 11
