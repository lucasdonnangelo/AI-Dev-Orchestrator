"""Event system for the orchestrator — pub/sub bus for cycle lifecycle events.

Usage::

    bus = EventBus()
    bus.subscribe(my_handler)          # sync or async callback
    await bus.emit(EventType.PLAN_STARTED, {"task": "..."})

Each event carries a ``run_id`` (unique per cycle), ``timestamp``, ``type``
and a ``data`` dict whose keys depend on the event type.

Event payload reference
-----------------------
PLAN_STARTED        task
PLAN_COMPLETED      task, plan (dict)
CRITIC_ROUND        round, score, consensus, observations, suggestions
CRITIC_CONSENSUS    round, score, plan (dict)
EXECUTE_STARTED     attempt, max_attempts
EXECUTE_COMPLETED   attempt, diff_lines
REVIEW_STARTED      attempt
REVIEW_COMPLETED    attempt, approved, score, issues_count
DECISION_STARTED    (empty)
DECISION_COMPLETED  approved, reasoning, inconsistencies
CYCLE_APPROVED      task, attempt
CYCLE_ESCALATED     task, reason
TOKEN_USAGE         agent, input_tokens, output_tokens, cost_usd (all optional)
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    PLAN_STARTED = "plan_started"
    PLAN_COMPLETED = "plan_completed"
    CRITIC_ROUND = "critic_round"
    CRITIC_CONSENSUS = "critic_consensus"
    EXECUTE_STARTED = "execute_started"
    EXECUTE_COMPLETED = "execute_completed"
    REVIEW_STARTED = "review_started"
    REVIEW_COMPLETED = "review_completed"
    DECISION_STARTED = "decision_started"
    DECISION_COMPLETED = "decision_completed"
    CYCLE_APPROVED = "cycle_approved"
    CYCLE_ESCALATED = "cycle_escalated"
    CYCLE_PAUSED = "cycle_paused"
    CYCLE_RESUMED = "cycle_resumed"
    TOKEN_USAGE = "token_usage"


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """A single lifecycle event emitted by the orchestrator."""

    type: EventType
    data: dict[str, Any]
    run_id: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "data": self.data,
        }


# ---------------------------------------------------------------------------
# Callback type alias
# ---------------------------------------------------------------------------

# Callbacks may be sync ``(Event) -> None`` or async ``async (Event) -> None``.
Callback = Callable[["Event"], Any]


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------

class EventBus:
    """Lightweight pub/sub bus scoped to a single orchestration cycle.

    One :class:`EventBus` is created per ``run_cycle`` call and carries a
    ``run_id`` that uniquely identifies that cycle.  Subscribers receive every
    event emitted during the cycle; they can be sync or async functions.

    Example::

        bus = EventBus()

        def on_event(event: Event) -> None:
            print(event.type, event.data)

        bus.subscribe(on_event)
        await bus.emit(EventType.PLAN_STARTED, {"task": "add tests"})
    """

    def __init__(self, run_id: str | None = None) -> None:
        self.run_id: str = run_id or str(uuid.uuid4())
        self._subscribers: list[Callback] = []

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def subscribe(self, callback: Callback) -> None:
        """Register *callback* to receive all future events."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callback) -> None:
        """Remove a previously registered *callback*.

        Raises ``ValueError`` if *callback* is not registered.
        """
        self._subscribers.remove(callback)

    # ------------------------------------------------------------------
    # Emission
    # ------------------------------------------------------------------

    async def emit(self, event_type: EventType, data: dict[str, Any] | None = None) -> None:
        """Emit *event_type* with optional *data* to all subscribers.

        Async subscribers are awaited sequentially.  Exceptions raised by
        individual subscribers are silently suppressed to avoid breaking the
        orchestration cycle — callers should handle errors inside their own
        callbacks.
        """
        event = Event(type=event_type, data=data or {}, run_id=self.run_id)
        for cb in self._subscribers:
            try:
                result = cb(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # noqa: BLE001
                pass  # never let a subscriber crash the orchestrator

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def subscriber_count(self) -> int:
        """Number of currently registered subscribers."""
        return len(self._subscribers)


# ---------------------------------------------------------------------------
# PauseController
# ---------------------------------------------------------------------------

class PauseController:
    """Pause / resume mechanism for an orchestration cycle.

    The orchestrator calls :meth:`check_pause` between pipeline stages.
    When the controller is paused (via :meth:`pause`), the call blocks
    until :meth:`resume` is called or the 30-minute timeout expires.

    Timeout raises :class:`TimeoutError` so that the background task
    transitions to the ``"error"`` state with an informative message.

    Example::

        ctrl = PauseController()

        # --- pause from the API layer ---
        ctrl.pause()

        # --- orchestrator blocks here until resume() is called ---
        edited_plan = await ctrl.check_pause()   # returns None or edited plan

        # --- resume (optionally with an edited plan) ---
        ctrl.resume(edited_plan=my_plan)
    """

    #: Maximum seconds to wait in a paused state before auto-cancelling.
    PAUSE_TIMEOUT: float = 1800.0  # 30 minutes

    def __init__(self) -> None:
        self._resume_event: asyncio.Event = asyncio.Event()
        self._resume_event.set()   # starts as "not paused"
        self._edited_plan: Any = None
        self._paused: bool = False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def is_paused(self) -> bool:
        """True if the cycle is currently paused."""
        return self._paused

    def pause(self) -> None:
        """Request a pause before the next pipeline stage.

        Idempotent — calling while already paused has no effect.
        """
        if not self._paused:
            self._paused = True
            self._resume_event.clear()

    def resume(self, edited_plan: Any = None) -> None:
        """Resume the cycle, optionally supplying an edited :class:`TaskPlan`.

        The plan (if any) is consumed by the next :meth:`check_pause` call
        and applied to the ongoing cycle.
        """
        self._edited_plan = edited_plan
        self._paused = False
        self._resume_event.set()

    async def check_pause(self) -> Any:
        """Block if paused; return the edited plan (or ``None``) when resumed.

        This method is called by the orchestrator between pipeline stages.
        If the controller is not paused it returns immediately with ``None``.

        Raises:
            TimeoutError: if the run stays paused for longer than
                :attr:`PAUSE_TIMEOUT` seconds (30 minutes by default).
        """
        if self._resume_event.is_set():
            return None  # fast path — not paused

        try:
            await asyncio.wait_for(self._resume_event.wait(), timeout=self.PAUSE_TIMEOUT)
        except asyncio.TimeoutError:
            # Unblock the event so the controller is in a clean state.
            self._paused = False
            self._resume_event.set()
            raise TimeoutError(
                "Run auto-cancelled: remained paused for more than 30 minutes"
            )

        plan = self._edited_plan
        self._edited_plan = None
        return plan
