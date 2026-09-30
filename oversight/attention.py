from __future__ import annotations


class AttentionTracker:
    """Tracks how much human attention is left. Time is injected, never read from a clock."""

    def __init__(self, window_seconds: float, max_interrupts: int, min_gap_seconds: float):
        self.window_seconds = window_seconds
        self.max_interrupts = max_interrupts
        self.min_gap_seconds = min_gap_seconds
        self._available = True
        self._times: list[float] = []

    def set_available(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available

    def interrupts_in_window(self, now: float) -> int:
        return sum(1 for t in self._times if now - t < self.window_seconds)

    def can_interrupt(self, now: float) -> tuple[bool, str]:
        if not self._available:
            return False, "human unavailable"
        if self._times and now - self._times[-1] < self.min_gap_seconds:
            return False, f"min gap {self.min_gap_seconds}s since last interrupt not met"
        used = self.interrupts_in_window(now)
        if used >= self.max_interrupts:
            return False, f"interrupt budget exhausted ({used}/{self.max_interrupts} in window)"
        return True, "human available within budget"

    def record_interrupt(self, now: float) -> None:
        self._times.append(now)
