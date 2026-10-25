"""How often the gate fails a pull request when nothing changed, and how often it catches a real drop.

Simulated suites only: each case passes each run with a fixed probability. The baseline runs every
case max_repeats times; a pull request runs it 3 times, and a case that looks worse gets topped up
to max_repeats, exactly as Suite.run does. The verdict comes from agent_ratchet.compare.

    python benchmarks/gate_simulation.py            # about two minutes
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_ratchet import CaseResult, CheckResult, RunResult, SuiteResult, Trajectory, compare  # noqa: E402
from agent_ratchet.suite import _looks_worse  # noqa: E402

FAIL = [CheckResult("check", False)]


def case(name: str, passes: int, n: int) -> CaseResult:
    return CaseResult(name, [RunResult(i, Trajectory(), [] if i < passes else FAIL) for i in range(n)])


def draws(n: int, p: float, rng: random.Random) -> int:
    return sum(rng.random() < p for _ in range(n))


def pull_request(base_rates: list[float], new_rates: list[float], rng: random.Random, repeats: int = 3, max_repeats: int = 10) -> tuple[set[str], int]:
    before, after, runs = [], [], 0
    for i, (pb, pn) in enumerate(zip(base_rates, new_rates, strict=True)):
        base = case(str(i), draws(max_repeats, pb, rng), max_repeats)
        passes, n = draws(repeats, pn, rng), repeats
        if _looks_worse(case(str(i), passes, n), base):
            passes, n = passes + draws(max_repeats - n, pn, rng), max_repeats
        before.append(base)
        after.append(case(str(i), passes, n))
        runs += n
    comparison = compare(SuiteResult("s", after), SuiteResult("s", before))
    return {d.name for d in comparison.regressions}, runs


SUITES = {
    "50 cases, all stable": [1.0] * 50,
    "50 cases, 10 pass 90% of the time": [1.0] * 40 + [0.9] * 10,
    "50 cases, 10 at 90%, 10 at 70%": [1.0] * 30 + [0.9] * 10 + [0.7] * 10,
    "200 cases, 30 at 90%, 20 at 60%": [1.0] * 150 + [0.9] * 30 + [0.6] * 20,
    "50 cases, every one at 50%": [0.5] * 50,
}
BACKGROUND = [1.0] * 30 + [0.9] * 10 + [0.7] * 9  # 49 other cases, 19 of them flaky
DROPS = [(1.0, 0.0), (1.0, 0.3), (1.0, 0.5), (1.0, 0.7), (0.9, 0.5)]


def main(sims: int = 2000) -> None:
    rng = random.Random(2026)
    print(f"Pull requests with no real change that fail ({sims} simulated each):")
    for name, rates in SUITES.items():
        failed = sum(bool(pull_request(rates, rates, rng)[0]) for _ in range(sims))
        print(f"  {name:36s} {failed / sims:5.1%}")
    print("\nOne case gets worse, among 49 others (19 flaky):")
    for max_repeats in (10, 20):
        print(f"  max_repeats={max_repeats}")
        for p0, p1 in DROPS:
            caught = runs = 0
            for _ in range(sims):
                flagged, n = pull_request(BACKGROUND + [p0], BACKGROUND + [p1], rng, max_repeats=max_repeats)
                caught += "49" in flagged
                runs += n
            print(f"    {p0:.0%} -> {p1:.0%}: caught {caught / sims:5.1%}, {runs / sims:.0f} agent runs per pull request")


if __name__ == "__main__":
    main()
