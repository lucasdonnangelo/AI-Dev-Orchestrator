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
