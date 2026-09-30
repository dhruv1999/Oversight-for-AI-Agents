"""When is the human reachable? Seeded schedules of unavailable intervals over one workday."""

from __future__ import annotations

import random
from dataclasses import dataclass

PROFILES = ("focused", "meetings", "away")


@dataclass(frozen=True)
class Schedule:
    profile: str
    day_seconds: int
    unavailable: tuple[tuple[int, int], ...]  # sorted, non-overlapping [start, end)

    def available(self, t: float) -> bool:
        return not any(s <= t < e for s, e in self.unavailable)

    def available_fraction(self) -> float:
        return 1 - sum(e - s for s, e in self.unavailable) / self.day_seconds


def _merge(iv: list[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    out: list[list[int]] = []
    for s, e in sorted(iv):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return tuple((s, e) for s, e in out)


def make_schedule(profile: str, rng: random.Random, day_seconds: int = 8 * 3600) -> Schedule:
    """focused: 1-3 meetings of 30-60 min.  meetings: back-to-back blocks, ~half the day away.
    away: an unattended run; the human checks in only during the first and last 30 minutes."""
    iv: list[tuple[int, int]] = []
    if profile == "focused":
        for _ in range(rng.randint(1, 3)):
            s = rng.randrange(0, day_seconds - 3600, 300)
            iv.append((s, s + rng.choice([1800, 2700, 3600])))
    elif profile == "meetings":
        t = rng.randrange(0, 3600, 300)
        while t < day_seconds:
            busy = rng.choice([1800, 2700, 3600])
            iv.append((t, min(day_seconds, t + busy)))
            t += busy + rng.choice([1800, 2700, 3600])
    elif profile == "away":
        iv.append((1800, day_seconds - 1800))
    else:
        raise ValueError(f"unknown profile {profile!r}")
    return Schedule(profile, day_seconds, _merge(iv))
