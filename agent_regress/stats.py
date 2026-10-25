"""Small statistics for small samples: agents are random, so every case runs several times."""

from __future__ import annotations

import math


def wilson(passes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% interval for a pass rate. Honest even with 3 or 5 runs, unlike the plain ratio."""
    if n == 0:
        return 0.0, 1.0
    p = passes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)
