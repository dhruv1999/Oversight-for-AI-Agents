"""Readable results: a table for the terminal and Markdown for pull requests and CI summaries."""

from __future__ import annotations

from .compare import IMPROVED, NEW, REGRESSED, REMOVED, Comparison
from .suite import CaseResult, SuiteResult


def _rate(c: CaseResult | None) -> str:
    return f"{c.passes}/{c.n}" if c else "-"


def _money(v: float | None) -> str:
    return f"${v:.4f}" if v is not None else "-"


def _secs(v: float | None) -> str:
    return f"{v:.1f}s" if v is not None else "-"


def _pct(v: float | None) -> str:
    return f"{v:+.0%}" if v is not None else ""


def text(result: SuiteResult, comparison: Comparison | None = None) -> str:
    diffs = {d.name: d for d in comparison.diffs} if comparison else {}
    rows = [("case", "passed", "baseline", "status", "cost", "time")]
    for c in result.cases:
        d = diffs.get(c.name)
        status = "ok" if c.always_passes else "flaky" if c.passes else "failing"
        if d and d.status == REGRESSED:
            status = "REGRESSED" + ("" if d.confident else " (check with more repeats)")
        elif d and d.status == IMPROVED:
            status = "improved"
        elif d and d.status == NEW:
            status += " (new)"
        rows.append((c.name, _rate(c), _rate(d.before) if d else "", status, _money(c.mean("cost_usd")), _secs(c.mean("latency_s"))))
    for d in comparison.diffs if comparison else []:
        if d.status == REMOVED:
            rows.append((d.name, "-", _rate(d.before), "removed", "", ""))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    lines = ["  ".join(v.ljust(w) for v, w in zip(r, widths, strict=True)).rstrip() for r in rows]
    lines.insert(1, "  ".join("-" * w for w in widths))

    details = []
    for c in result.cases:
        d = diffs.get(c.name)
        if d and d.status == REGRESSED:
            details += [f"{c.name}: pass rate {d.before.pass_rate:.0%} -> {c.pass_rate:.0%}" if d.before else c.name]
            details += [f"  {n}" for n in d.notes]
        elif not c.always_passes:
            details.append(f"{c.name}:")
            for check, count in c.failing_checks.most_common(3):
                example = c.example_failure(check)
                details.append(f"  {check}: failed {count}/{c.n}" + (f" ({example})" if example else ""))
    if comparison:
        for d in comparison.over_budget:
            details.append(f"{d.name}: cost {_pct(d.cost_change)}, time {_pct(d.latency_change)} over the allowed increase")

    total_runs = sum(c.n for c in result.cases)
    passed_runs = sum(c.passes for c in result.cases)
    summary = f"{passed_runs}/{total_runs} runs passed across {len(result.cases)} cases"
    if comparison:
        summary += f"; {len(comparison.regressions)} regressed"
    return "\n".join(lines + ([""] + details if details else []) + ["", summary])


def markdown(result: SuiteResult, comparison: Comparison | None = None) -> str:
    diffs = {d.name: d for d in comparison.diffs} if comparison else {}
    regressed = len(comparison.regressions) if comparison else 0
    head = f"### agent-regress: {result.name}\n\n"
    head += f"**{regressed} regressed**, " if comparison else ""
    head += f"{sum(c.always_passes for c in result.cases)}/{len(result.cases)} cases passed every run.\n\n"
    lines = ["| Case | Passed | Baseline | Status | Cost | Time |", "|---|---|---|---|---|---|"]
    for c in result.cases:
        d = diffs.get(c.name)
        status = "✅ ok" if c.always_passes else "⚠️ flaky" if c.passes else "❌ failing"
        if d and d.status == REGRESSED:
            status = "🔻 regressed" + ("" if d.confident else " (rerun with more repeats)")
        elif d and d.status == IMPROVED:
            status = "🔺 improved"
        cost = _money(c.mean("cost_usd")) + (f" ({_pct(d.cost_change)})" if d and d.cost_change is not None else "")
        lines.append(f"| {c.name} | {_rate(c)} | {_rate(d.before) if d else ''} | {status} | {cost} | {_secs(c.mean('latency_s'))} |")
    notes = []
    for c in result.cases:
        d = diffs.get(c.name)
        if d and d.status == REGRESSED and d.notes:
            notes.append(f"- **{c.name}**: " + "; ".join(d.notes))
    return head + "\n".join(lines) + ("\n\n" + "\n".join(notes) if notes else "") + "\n"
