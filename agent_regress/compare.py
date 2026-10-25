"""Compare a run with a saved baseline and decide what got worse.

A case has regressed when its pass rate drops by at least `tolerance` (30 points by default).
Small samples are noisy, so the report also shows each pass rate's 95% interval and marks drops
whose intervals still overlap as "check with more repeats". Cost and latency increases are
reported, and only fail the comparison when you ask for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .suite import CaseResult, SuiteResult

REGRESSED, IMPROVED, SAME, NEW, REMOVED = "regressed", "improved", "same", "new", "removed"


@dataclass
class CaseDiff:
    name: str
    status: str
    before: CaseResult | None
    after: CaseResult | None
    notes: list[str] = field(default_factory=list)
    confident: bool = True  # False when the pass rate intervals overlap
    cost_change: float | None = None  # relative, e.g. 0.4 for 40% more
    latency_change: float | None = None

    @property
    def change(self) -> float:
        b = self.before.pass_rate if self.before else 0.0
        a = self.after.pass_rate if self.after else 0.0
        return a - b


@dataclass
class Comparison:
    diffs: list[CaseDiff]
    max_cost_increase: float | None = None
    max_latency_increase: float | None = None

    @property
    def regressions(self) -> list[CaseDiff]:
        return [d for d in self.diffs if d.status == REGRESSED]

    @property
    def over_budget(self) -> list[CaseDiff]:
        out = []
        for d in self.diffs:
            if self.max_cost_increase is not None and d.cost_change is not None and d.cost_change > self.max_cost_increase:
                out.append(d)
            elif self.max_latency_increase is not None and d.latency_change is not None and d.latency_change > self.max_latency_increase:
                out.append(d)
        return out

    @property
    def ok(self) -> bool:
        return not self.regressions and not self.over_budget


def _relative(before: float | None, after: float | None) -> float | None:
    if before is None or after is None or before <= 0:
        return None
    return after / before - 1


def compare(
    after: SuiteResult,
    before: SuiteResult,
    tolerance: float = 0.3,
    max_cost_increase: float | None = None,
    max_latency_increase: float | None = None,
) -> Comparison:
    diffs = []
    for case in after.cases:
        base = before.case(case.name)
        if base is None:
            diffs.append(CaseDiff(case.name, NEW, None, case))
            continue
        drop = base.pass_rate - case.pass_rate
        status = REGRESSED if drop >= tolerance - 1e-9 else IMPROVED if -drop >= tolerance - 1e-9 else SAME
        lo_b, hi_b = base.interval
        lo_a, hi_a = case.interval
        confident = hi_a < lo_b if status == REGRESSED else lo_a > hi_b if status == IMPROVED else True
        notes = []
        if status == REGRESSED:
            new_fails = case.failing_checks - base.failing_checks
            for check, count in new_fails.most_common(3):
                example = case.example_failure(check)
                notes.append(f"{check}: failed {count}/{case.n}" + (f" ({example})" if example else ""))
        diffs.append(
            CaseDiff(
                case.name,
                status,
                base,
                case,
                notes,
                confident,
                _relative(base.mean("cost_usd"), case.mean("cost_usd")),
                _relative(base.mean("latency_s"), case.mean("latency_s")),
            )
        )
    for base in before.cases:
        if after.case(base.name) is None:
            diffs.append(CaseDiff(base.name, REMOVED, base, None))
    return Comparison(diffs, max_cost_increase, max_latency_increase)
