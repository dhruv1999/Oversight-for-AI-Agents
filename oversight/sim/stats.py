"""Small, dependency free statistics used by the experiment scripts."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from typing import Any


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion. Well behaved at 0 and n, unlike the normal approximation."""
    if n == 0:
        return 0.0, 1.0
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def ratio_ci(num: Sequence[float], den: Sequence[float], rng: random.Random, n: int = 1000) -> tuple[float, float]:
    """Bootstrap (over units, e.g. workdays) CI of sum(num) / sum(den)."""
    idx = range(len(num))
    stats = []
    for _ in range(n):
        s = [rng.choice(idx) for _ in idx]
        d = sum(den[i] for i in s)
        stats.append(sum(num[i] for i in s) / d if d else 0.0)
    stats.sort()
    return stats[int(0.025 * n)], stats[int(0.975 * n) - 1]


def paired_difference(a: list[dict[str, Any]], b: list[dict[str, Any]], rng: random.Random, n: int = 2000) -> dict[str, Any]:
    """a minus b on the SAME episodes (same actions, schedule and human luck), bootstrapped over episodes.

    Reports harm executed (percentage points of harmful actions) and interrupts per day.
    """
    if len(a) != len(b) or not a:
        raise ValueError("paired comparison needs two equally long, non empty lists of episodes")
    idx = range(len(a))

    def stats(sample: Sequence[int]) -> tuple[float, float]:
        ha = sum(a[i]["harmful_executed"] for i in sample) / max(1, sum(a[i]["harmful"] for i in sample))
        hb = sum(b[i]["harmful_executed"] for i in sample) / max(1, sum(b[i]["harmful"] for i in sample))
        ia = sum(a[i]["interrupts"] for i in sample) / len(sample)
        ib = sum(b[i]["interrupts"] for i in sample) / len(sample)
        return 100 * (ha - hb), ia - ib

    point = stats(list(idx))
    draws = [stats([rng.choice(idx) for _ in idx]) for _ in range(n)]
    harm = sorted(d[0] for d in draws)
    intr = sorted(d[1] for d in draws)
    lo, hi = int(0.025 * n), int(0.975 * n) - 1
    return {
        "harm_diff_points": point[0],
        "harm_diff_ci95": [harm[lo], harm[hi]],
        "interrupts_diff_per_day": point[1],
        "interrupts_diff_ci95": [intr[lo], intr[hi]],
        "episodes": len(a),
    }
