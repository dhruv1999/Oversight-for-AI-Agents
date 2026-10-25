"""Readable results: a table for the terminal and Markdown for pull requests and CI summaries."""

from __future__ import annotations

from .compare import CHANGED, IMPROVED, NEW, REGRESSED, REMOVED, CaseDiff, Comparison
from .suite import CaseResult, SuiteResult

STALE_DAYS = 30  # older baselines get a reminder: providers update models behind the same name


def _rate(c: CaseResult | None) -> str:
    return f"{c.passes}/{c.n}" if c else "-"


def _money(v: float | None) -> str:
    return f"${v:.4f}" if v is not None else "-"


def _secs(v: float | None) -> str:
    return f"{v:.1f}s" if v is not None else "-"


def _pct(v: float | None) -> str:
    return f"{v:+.0%}" if v is not None else ""


def _chance(p: float | None) -> str:
    return "?" if p is None else "under 0.1%" if p < 0.001 else f"{p:.1%}"


def _plain(c: CaseResult) -> str:
    return "ok" if c.always_passes else "flaky" if c.passes else "failing"


def _status(c: CaseResult, d: CaseDiff | None) -> str:
    if c.must_pass_failed:
        return "FAILED (must pass)"
    if d is not None and d.status == REGRESSED:
        return "REGRESSED"
    if d is not None and d.status == IMPROVED:
        return "improved"
    if d is not None and d.status in (NEW, CHANGED):
        return f"{_plain(c)} ({d.status})"
    return _plain(c)


def _failures(c: CaseResult) -> list[str]:
    lines = []
    for check, count in c.failing_checks.most_common(3):
        example = c.example_failure(check)
        lines.append(f"  {check}: failed {count}/{c.n}" + (f" ({example})" if example else ""))
    return lines


def _explain(c: CaseResult, d: CaseDiff | None) -> list[str]:
    """Plain language lines for a case that needs attention. Cases as good as their baseline stay quiet."""
    b = d.before if d is not None else None
    if d is not None and b is not None and d.status == REGRESSED:
        head = f"{c.name}: passed {c.passes}/{c.n}, baseline {b.passes}/{b.n}. A drop this large happens by chance {_chance(d.chance)} of the time."
        return [head] + [f"  {n}" for n in d.notes]
    if c.must_pass_failed:
        return [f"{c.name}: must pass, but failed {c.n - c.passes} of {c.n} runs"] + _failures(c)
    if d is not None and b is not None and d.looks_worse:
        return [f"{c.name}: passed {c.passes}/{c.n}, baseline {b.passes}/{b.n}. That could be chance ({_chance(d.chance)}); raise --max-repeats to be sure."]
    if d is not None and d.status == CHANGED:
        return [f"{c.name}: its input or checks changed since the baseline, so it was not compared. Save a new baseline."]
    if not c.always_passes and (d is None or d.status == NEW):
        return [f"{c.name}:"] + _failures(c)
    return []


def _notes(result: SuiteResult, comparison: Comparison | None) -> list[str]:
    diffs = {d.name: d for d in comparison.diffs} if comparison else {}
    lines = [line for c in result.cases for line in _explain(c, diffs.get(c.name))]
    if comparison:
        for d in comparison.over_budget:
            lines.append(f"{d.name}: cost {_pct(d.cost_change)}, time {_pct(d.latency_change)}, over the allowed increase")
        age = comparison.baseline_age_days
        if age is not None and age > STALE_DAYS:
            lines.append(f"The baseline is {age} days old. Providers update models behind the same name; refresh it from your main branch now and then.")
    return lines


def _summary(result: SuiteResult, comparison: Comparison | None) -> str:
    total = sum(c.n for c in result.cases)
    passed = sum(c.passes for c in result.cases)
    parts = [f"{passed}/{total} runs passed across {len(result.cases)} cases"]
    if comparison:
        parts.append(f"{len(comparison.regressions)} regressed")
    if result.must_pass_failures:
        parts.append(f"{len(result.must_pass_failures)} must pass cases failed")
    if result.cost_usd is not None:
        parts.append(f"cost ${result.cost_usd:.4f}")
    return "; ".join(parts)


def text(result: SuiteResult, comparison: Comparison | None = None) -> str:
    diffs = {d.name: d for d in comparison.diffs} if comparison else {}
    rows = [("case", "passed", "baseline", "status", "cost", "time")]
    for c in result.cases:
        d = diffs.get(c.name)
        before = d.before if d is not None and d.status not in (NEW, CHANGED) else None
        rows.append((c.name, _rate(c), _rate(before) if d else "", _status(c, d), _money(c.mean("cost_usd")), _secs(c.mean("latency_s"))))
    for d in comparison.diffs if comparison else []:
        if d.status == REMOVED:
            rows.append((d.name, "-", _rate(d.before), "removed", "", ""))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    lines = ["  ".join(v.ljust(w) for v, w in zip(r, widths, strict=True)).rstrip() for r in rows]
    lines.insert(1, "  ".join("-" * w for w in widths))
    notes = _notes(result, comparison)
    return "\n".join(lines + ([""] + notes if notes else []) + ["", _summary(result, comparison)])


_ICONS = {"ok": "✅ ok", "flaky": "⚠️ flaky", "failing": "❌ failing"}


def _md(s: str) -> str:
    return s.replace("|", "\\|")


def markdown(result: SuiteResult, comparison: Comparison | None = None) -> str:
    diffs = {d.name: d for d in comparison.diffs} if comparison else {}
    head = f"### agent-ratchet: {_md(result.name)}\n\n"
    verdict = []
    if comparison:
        verdict.append(f"**{len(comparison.regressions)} regressed**")
    if result.must_pass_failures:
        verdict.append(f"**{len(result.must_pass_failures)} must pass cases failed**")
    every = sum(c.always_passes for c in result.cases)
    head += (", ".join(verdict) + ". " if verdict else "") + f"{every}/{len(result.cases)} cases passed every run.\n\n"
    lines = ["| Case | Passed | Baseline | Status | Cost | Time |", "|---|---|---|---|---|---|"]
    for c in result.cases:
        d = diffs.get(c.name)
        status = _status(c, d)
        if c.must_pass_failed:
            status = "❌ failed (must pass)"
        elif status in ("REGRESSED", "improved"):
            status = "🔻 regressed" if status == "REGRESSED" else "🔺 improved"
        for plain, icon in _ICONS.items():
            if status.startswith(plain):
                status = icon + status[len(plain) :]
        before = d.before if d is not None and d.status not in (NEW, CHANGED) else None
        cost = _money(c.mean("cost_usd")) + (f" ({_pct(d.cost_change)})" if d and d.cost_change is not None else "")
        lines.append(f"| {_md(c.name)} | {_rate(c)} | {_rate(before) if d else ''} | {status} | {cost} | {_secs(c.mean('latency_s'))} |")
    notes = _notes(result, comparison)
    body = "\n".join(f"- {_md(n.strip())}" if not n.startswith("  ") else f"  - {_md(n.strip())}" for n in notes)
    return head + "\n".join(lines) + ("\n\n" + body if body else "") + f"\n\n{_md(_summary(result, comparison))}\n"
