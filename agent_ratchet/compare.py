"""Compare a run with a saved baseline and decide which cases got worse.

Each case is a pass rate over several runs. A case has regressed when its pass rate dropped by more
than chance explains: a one sided Fisher exact test per case, with the threshold adjusted across the
suite (Tarone's method) so that a suite with no real change fails less than 5% of the time, however
many cases it has. A case whose input or checks were edited since the baseline is reported as
changed instead of being compared with a baseline that no longer fits it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .stats import fisher_worse, min_p_worse, tarone
from .suite import CaseResult, SuiteResult

REGRESSED, IMPROVED, SAME, NEW, CHANGED, REMOVED = "regressed", "improved", "same", "new", "changed", "removed"


@dataclass
class CaseDiff:
    name: str
    status: str
    before: CaseResult | None
    after: CaseResult | None
    notes: list[str] = field(default_factory=list)
    chance: float | None = None  # how likely a change this large is with no real change (one sided p-value)
    cost_change: float | None = None  # relative, e.g. 0.4 for 40% more
    latency_change: float | None = None

    @property
    def looks_worse(self) -> bool:
        """A lower pass rate that is still within chance: worth more runs, not a failed build."""
        return self.status == SAME and self.before is not None and self.after is not None and self.after.pass_rate < self.before.pass_rate


@dataclass
class Comparison:
    diffs: list[CaseDiff]
    confidence: float = 0.95
    max_cost_increase: float | None = None
    max_latency_increase: float | None = None
    baseline_created: str = ""

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

    @property
    def baseline_age_days(self) -> int | None:
        try:
            created = datetime.fromisoformat(self.baseline_created)
        except ValueError:
            return None
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - created).days


def _relative(before: float | None, after: float | None) -> float | None:
    if before is None or after is None or before <= 0:
        return None
    return after / before - 1


def _worse_checks(base: CaseResult, case: CaseResult) -> list[str]:
    """Checks that fail more often than in the baseline, with an example of the failure."""
    notes = []
    for check, count in case.failing_checks.most_common():
        before = base.failing_checks.get(check, 0)
        if count / case.n > before / base.n:
            example = case.example_failure(check)
            notes.append(f"{check}: failed {count}/{case.n}, baseline {before}/{base.n}" + (f" ({example})" if example else ""))
    return notes[:3]


def compare(
    after: SuiteResult,
    before: SuiteResult,
    confidence: float = 0.95,
    max_cost_increase: float | None = None,
    max_latency_increase: float | None = None,
) -> Comparison:
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1, e.g. 0.95")
    alpha = 1 - confidence
    diffs: list[CaseDiff] = []
    tested: list[CaseDiff] = []
    for case in after.cases:
        base = before.case(case.name)
        if base is None:
            diffs.append(CaseDiff(case.name, NEW, None, case))
        elif base.fingerprint and case.fingerprint and base.fingerprint != case.fingerprint:
            diffs.append(CaseDiff(case.name, CHANGED, base, case))
        else:
            d = CaseDiff(
                case.name,
                SAME,
                base,
                case,
                cost_change=_relative(base.mean("cost_usd"), case.mean("cost_usd")),
                latency_change=_relative(base.mean("latency_s"), case.mean("latency_s")),
            )
            diffs.append(d)
            tested.append(d)

    pairs = [(d, d.before, d.after) for d in tested if d.before is not None and d.after is not None and d.before.n and d.after.n]
    worse_at = tarone(alpha, [min_p_worse(b.passes, b.n, a.passes, a.n) for _, b, a in pairs])
    better_at = tarone(alpha, [min_p_worse(a.passes, a.n, b.passes, b.n) for _, b, a in pairs])
    for d, b, a in pairs:
        if a.pass_rate < b.pass_rate:
            d.chance = fisher_worse(b.passes, b.n, a.passes, a.n)
            if d.chance <= worse_at * (1 + 1e-9):
                d.status = REGRESSED
                d.notes = _worse_checks(b, a)
        elif a.pass_rate > b.pass_rate:
            d.chance = fisher_worse(a.passes, a.n, b.passes, b.n)
            if d.chance <= better_at * (1 + 1e-9):
                d.status = IMPROVED

    for base in before.cases:
        if after.case(base.name) is None:
            diffs.append(CaseDiff(base.name, REMOVED, base, None))
    return Comparison(diffs, confidence, max_cost_increase, max_latency_increase, before.created)
