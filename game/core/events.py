"""Lightweight synchronous event bus.

Systems publish gameplay events (unit_destroyed, research_complete, ...) that the
mission system, UI and audio subscribe to. Keeps systems decoupled: the combat
system never imports the mission system.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(slots=True)
class GameEvent:
    type: str
    data: dict = field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[GameEvent], None]]] = defaultdict(list)
        self._any_subs: list[Callable[[GameEvent], None]] = []
        self.log: list[GameEvent] = []          # ring for debugging/saves
        self.log_limit = 400

    def subscribe(self, etype: str, fn: Callable[[GameEvent], None]) -> None:
        self._subs[etype].append(fn)

    def subscribe_any(self, fn: Callable[[GameEvent], None]) -> None:
        self._any_subs.append(fn)

    def publish(self, etype: str, **data: Any) -> None:
        ev = GameEvent(etype, data)
        self.log.append(ev)
        if len(self.log) > self.log_limit:
            del self.log[: len(self.log) - self.log_limit]
        for fn in self._subs.get(etype, ()):
            fn(ev)
        for fn in self._any_subs:
            fn(ev)

    def clear(self) -> None:
        self._subs.clear()
        self._any_subs.clear()
        self.log.clear()