from __future__ import annotations

import bisect
from collections.abc import Iterable
from typing import Any


class AttentionTracker:
    """Tracks how much human attention is left. Time is injected, never read from a clock.

    Only interrupts inside the current window are kept, so memory stays bounded in a
    long running process. Pass keep_history=True to also keep every interrupt (used by
    the simulator to report the busiest hour).
    """

    def __init__(self, window_seconds: float, max_interrupts: int, min_gap_seconds: float, keep_history: bool = False):
        if window_seconds <= 0 or max_interrupts < 0 or min_gap_seconds < 0:
            raise ValueError("window_seconds must be > 0; max_interrupts and min_gap_seconds must be >= 0")
        self.window_seconds = window_seconds
        self.max_interrupts = max_interrupts
        self.min_gap_seconds = min_gap_seconds
        self._available = True
        self._times: list[float] = []  # sorted, pruned to the window
        self._history: list[float] | None = [] if keep_history else None

    @classmethod
    def from_config(cls, cfg: dict[str, Any], keep_history: bool = False) -> AttentionTracker:
        return cls(cfg["window_seconds"], cfg["max_interrupts_per_window"], cfg["min_gap_seconds"], keep_history)

    def set_available(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available

    def interrupt_times(self) -> list[float]:
        """Interrupts still inside the window (for persisting state between processes)."""
        return list(self._times)

    def history(self) -> list[float]:
        if self._history is None:
            raise RuntimeError("history is only kept when keep_history=True")
        return list(self._history)

    def restore(self, times: Iterable[float]) -> None:
        for t in times:
            self.record_interrupt(t)

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
        if self._history is not None:
            bisect.insort(self._history, now)
        cutoff = self._times[-1] - self.window_seconds
        drop = bisect.bisect_right(self._times, cutoff)
        if drop:
            del self._times[:drop]
