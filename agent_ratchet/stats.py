"""The statistics behind a verdict.

Agents are random, so a case passes some share of its runs. A drop only counts when it is larger
than chance explains:

- `fisher_worse` is a one sided Fisher exact test on two pass counts: the chance of a drop at least
  this large if nothing changed. It is exact for small samples, where most rules of thumb fail.
- `tarone` picks the per case threshold that keeps the chance of any false alarm in the whole suite
  at `alpha`. It only counts cases that could reach significance (Tarone, 1990), so a suite full of
  stable cases does not make the gate less sensitive.
"""

from __future__ import annotations

from collections.abc import Iterable
from math import comb


def fisher_worse(base_passes: int, base_runs: int, passes: int, runs: int) -> float:
    """Chance of a drop at least this large if both samples came from the same pass rate."""
    total, passed = base_runs + runs, base_passes + passes
    top = min(base_runs, passed)
    hits = sum(comb(passed, x) * comb(total - passed, base_runs - x) for x in range(base_passes, top + 1))
    return hits / comb(total, base_runs)


def min_p_worse(base_passes: int, base_runs: int, passes: int, runs: int) -> float:
    """The smallest value fisher_worse could take with these totals (every failure in the new runs)."""
    total, passed = base_runs + runs, base_passes + passes
    top = min(base_runs, passed)
    return comb(passed, top) * comb(total - passed, base_runs - top) / comb(total, base_runs)


def tarone(alpha: float, min_ps: Iterable[float]) -> float:
    """Bonferroni threshold that only counts tests able to reach significance."""
    mins = list(min_ps)
    for k in range(1, len(mins) + 1):
        if sum(m <= alpha / k for m in mins) <= k:
            return alpha / k
    return alpha / max(len(mins), 1)
