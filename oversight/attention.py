from __future__ import annotations

import bisect
from typing import Any


class AttentionTracker:
    """Tracks how much human attention is left. Time is injected, never read from a clock."""

    def __init__(self, window_seconds: float, max_interrupts: int, min_gap_seconds: float):
        self.window_seconds = window_seconds
        self.max_interrupts = max_interrupts
        self.min_gap_seconds = min_gap_seconds
        self._available = True
        self._times: list[float] = []  # kept sorted

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> AttentionTracker:
        return cls(cfg["window_seconds"], cfg["max_interrupts_per_window"], cfg["min_gap_seconds"])

    def set_available(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available

    def interrupts_in_window(self, now: float) -> int:
        return sum(1 for t in self._times if 0 <= now - t < self.window_seconds)

    def can_interrupt(self, now: float) -> tuple[bool, str]:
        if not self._available:
            return False, "human unavailable"
        past = [t for t in self._times if t <= now]
        if past and now - past[-1] < self.min_gap_seconds:
            return False, f"min gap {self.min_gap_seconds}s since last interrupt not met"
        used = self.interrupts_in_window(now)
        if used >= self.max_interrupts:
            return False, f"interrupt budget exhausted ({used}/{self.max_interrupts} in window)"
        return True, "human available within budget"

    def earliest_interrupt_time(self, now: float) -> float | None:
        """Earliest t >= now at which the budget and gap allow an interrupt (ignores availability)."""
        if self.max_interrupts <= 0:
            return None
        t = now
        past = [x for x in self._times if x <= now]
        if past:
            t = max(t, past[-1] + self.min_gap_seconds)
        in_window = [x for x in past if now - x < self.window_seconds]
        if len(in_window) >= self.max_interrupts:
            # the oldest interrupts must age out until one slot is free
            t = max(t, in_window[len(in_window) - self.max_interrupts] + self.window_seconds)
        return t

    def record_interrupt(self, now: float) -> None:
        bisect.insort(self._times, now)
