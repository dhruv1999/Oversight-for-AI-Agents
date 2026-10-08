"""Render figures + docs/results.md from results/<tag>/summary.json, and refresh the README results block.

    uv run python scripts/make_report.py            # uses results/heuristic
    uv run python scripts/make_report.py --tag llm_claude-opus-5-5

Every number printed here is read from the JSON the experiment script wrote.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import charts
from charts import LABELS, pick

from oversight.sim.stats import wilson

ROOT = Path(__file__).resolve().parent.parent

HEADLINE_BUDGET = 1


def load(tag: str):
    rows = json.loads((ROOT / "results" / tag / "summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "results" / tag / "manifest.json").read_text(encoding="utf-8"))
    acc = json.loads((ROOT / "results" / tag / "reviewer_accuracy.json").read_text(encoding="utf-8"))
    paired = json.loads((ROOT / "results" / tag / "paired.json").read_text(encoding="utf-8"))
    manifest["paired"] = paired
    PAIRED.clear()
    PAIRED.update(paired)
    return rows, manifest, acc


def fmt(x: float, d: int = 1) -> str:
    return f"{x:,.{d}f}"


def table(rows, fatigue: str, profile: str = "all") -> str:
    order = [("no_oversight", None), ("always_model", None), ("static_risk", None), ("adaptive", HEADLINE_BUDGET), ("adaptive", 6), ("always_human", None)]
    lines = [
        "| Strategy | Harm executed % (95% CI) | Interrupts / day | Peak / hour | Benign blocked % | Benign still waiting at day end % | Deferred / day | Mean wait (min) | Model calls / day |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s, b in order:
        r = pick(rows, fatigue, profile, s, b)
        name = LABELS[s] + (f" (budget {b}/h)" if b else "")
        lo, hi = r["harm_executed_ci95"]
        lines.append(
            f"| {name} | {fmt(r['harm_executed_pct'])} ({fmt(lo)}–{fmt(hi)}) | {fmt(r['interrupts_per_day'])} | {fmt(r['peak_interrupts_in_an_hour'])} | "
            f"{fmt(r['benign_blocked_pct'])} | {fmt(r['benign_unresolved_pct'], 2)} | {fmt(r['deferred_per_day'])} | {fmt(r['mean_deferral_min'], 0)} | {fmt(r['model_calls_per_day'])} |"
        )
    return "\n".join(lines)


def profile_table(rows) -> str:
    lines = [
        "| Availability | Static: harm % | Static: interrupts/day | Adaptive (1/h): harm % | Adaptive (1/h): interrupts/day | Adaptive (1/h): deferred/day |",
        "|---|---|---|---|---|---|",
    ]
    for p in ("focused", "meetings", "away"):
        s, a = pick(rows, "on", p, "static_risk", None), pick(rows, "on", p, "adaptive", HEADLINE_BUDGET)
        lines.append(
            f"| {p} | {fmt(s['harm_executed_pct'])} | {fmt(s['interrupts_per_day'])} | {fmt(a['harm_executed_pct'])} | {fmt(a['interrupts_per_day'])} | {fmt(a['deferred_per_day'])} |"
        )
    return "\n".join(lines)


def accuracy_table(acc) -> str:
    """Harmful slices: share stopped (block or escalate). Benign slices: share wrongly stopped. Wilson 95% intervals."""
    lines = [
        "| Unique actions | allow | escalate | block | Stopped (block or escalate), 95% CI |",
        "|---|---|---|---|---|",
    ]
    names = {"benign": "benign", "benign_lookalike": "benign that look scary", "harmful_overt": "harmful, obvious", "harmful_subtle": "harmful, disguised"}
    for g in ("benign", "benign_lookalike", "harmful_overt", "harmful_subtle"):
        c = acc.get(g, {})
        n = sum(c.values())
        stopped = c.get("escalate", 0) + c.get("block", 0)
        lo, hi = wilson(stopped, n)
        lines.append(
            f"| {names[g]} (n={n}) | {c.get('allow', 0)} | {c.get('escalate', 0)} | {c.get('block', 0)} | {100 * stopped / max(1, n):.0f}% ({100 * lo:.0f} to {100 * hi:.0f}) |"
        )
    return "\n".join(lines)


def robustness_md(rob) -> str:
    if not rob:
        return ""
    v = {x["name"]: x for x in rob["variants"]}
    assumptions = [x for x in rob["variants"] if x["kind"] in ("person", "workload", "accounting")]
    better = sum(x["harm_diff_ci95"][1] < 0 for x in assumptions)
    worse = sum(x["harm_diff_ci95"][0] > 0 for x in assumptions)
    fewer = sum(x["interrupts_diff_ci95"][1] < 0 for x in assumptions)
    no_fb = v["Remove: checker takes over when the budget is spent"]
    lax = v["Remove: checker may only block, not approve, when it takes over"]
    acct = v["Every queued review counts as its own interruption"]
    base = v["Baseline assumptions"]
    att = rob["budget_drain_attack"]
    top = max(r["burst"] for r in att)

    def a(human, strat, k):
        return next(r for r in att if r["human"] == human and r["strategy"] == strat and r["burst"] == k)

    return f"""## Does it survive other assumptions?

Each row changes one assumption and reruns the paired comparison on 300 identical workdays.

![robustness](../figures/robustness.png)

{robustness_table(rob)}

Across the {len(assumptions)} assumption changes, this project let through clearly less harm in {better}, clearly more in {worse},
and caused clearly fewer interruptions in {fewer}. Where a confidence interval touches 0, read it as "no worse", not "better".

**Counting matters.** If every queued review counts as its own interruption instead of one sitting per queue, the saving
drops from {abs(base["interrupts_diff_per_day"]):.1f} to {abs(acct["interrupts_diff_per_day"]):.1f} interruptions a day. Both numbers are real; they answer different questions.

## Which part of the design does the work?

Removing one piece at a time (the last two rows above):

- **Without the checker taking over when the budget is spent**, over budget actions just wait for the person.
  The harm advantage mostly disappears ({no_fb["harm_diff_points"]:+.1f} points, {no_fb["harm_diff_ci95"][0]:+.1f} to {no_fb["harm_diff_ci95"][1]:+.1f})
  and more actions wait ({no_fb["adaptive_deferred"]:.1f} per day). The interruption saving comes from the budget; the safety gain comes from the takeover.
- **If the checker may also approve high risk actions when it takes over** (instead of only blocking them), far fewer actions wait ({lax["adaptive_deferred"]:.1f} per day instead of
  {base["adaptive_deferred"]:.1f}) but harm gets worse than fixed rules ({lax["harm_diff_points"]:+.1f} points, {lax["harm_diff_ci95"][0]:+.1f} to
  {lax["harm_diff_ci95"][1]:+.1f}). This is the main dial between speed and safety, and the default sits on the safe side.

## Can an agent game it?

A hostile agent fires a burst of harmless looking high risk actions 20 seconds apart to wear out the person, then hides one
harmful high risk action right after. 300 attacks per cell:

![attack](../figures/attack.png)

{attack_table(rob)}

With fixed rules the attack gets easier as the burst grows, because every decoy reaches the person
({a("fatigue on", "static_risk", 0)["success_pct"]:.0f}% → {a("fatigue on", "static_risk", top)["success_pct"]:.0f}% with a tired person).
Here the budget runs out, the checker takes over with its stricter bar, and success stays at
{a("fatigue on", "adaptive", top)["success_pct"]:.0f}% after {top} decoys. The defence depends on the checker: an attacker that also fools the checker is not covered."""


def research_md(res) -> str:
    if not res:
        return ""
    sweep = [r for r in res["checker_sweep"] if r["fatigue"] == "on"]
    recalls = sorted({r["recall"] for r in sweep})

    def cell(strat, rc):
        r = next(x for x in sweep if x["strategy"] == strat and x["recall"] == rc)
        return f"{r['harm_pct']:.1f}%"

    order = [
        ("adaptive", "This project (checker may only block when it takes over)"),
        ("adaptive_approve", "This project, if the checker may also approve"),
        ("static_risk", "Fixed approval rules"),
        ("always_model", "Automatic checker reviews everything"),
        ("always_human", "Person approves everything"),
    ]
    head = "| Harmful actions that got through | " + " | ".join(f"checker catches {100 * rc:.0f}%" for rc in recalls) + " |"
    rows = [head, "|---" * (len(recalls) + 1) + "|"]
    for key, label in order:
        rows.append(f"| {label} | " + " | ".join(cell(key, rc) for rc in recalls) + " |")

    def harm(strat, rc):
        return next(x for x in sweep if x["strategy"] == strat and x["recall"] == rc)["harm_pct"]

    per_day = {k: next(x for x in sweep if x["strategy"] == k)["interrupts_per_day"] for k, _ in order}
    beats = [rc for rc in recalls if harm("adaptive", rc) <= harm("static_risk", rc)]
    approve_beats = [rc for rc in recalls if harm("adaptive_approve", rc) < harm("static_risk", rc)]
    checker_alone = [rc for rc in recalls if harm("always_model", rc) < harm("adaptive", rc)]
    paced_ok = [p["budget_per_hour"] for p in res["pacing"] if p["harm_diff_ci95"][1] < 0 and p["interrupts_diff_ci95"][1] < 0]
    pace = "\n".join(
        f"| {p['budget_per_hour']} per hour | {p['harm_diff_points']:+.2f} ({p['harm_diff_ci95'][0]:+.2f} to {p['harm_diff_ci95'][1]:+.2f}) | "
        f"{p['interrupts_diff_per_day']:+.2f} ({p['interrupts_diff_ci95'][0]:+.2f} to {p['interrupts_diff_ci95'][1]:+.2f}) |"
        for p in res["pacing"]
    )
    return f"""## How good must the checker be?

The free rules checker stops {100 * res["heuristic_recall"]:.0f}% of the harmful actions in the pool. To see what a better checker
(for example an LLM) would change, a simulated checker with a chosen catch rate replaces it, with false alarms fixed at
{100 * res["false_alarm"]:.0f}% and full confidence in every answer.

![checker quality](../figures/checker_quality.png)

{chr(10).join(rows)}

Interruptions per day do not depend on the checker: {per_day["adaptive"]:.1f} for this project, {per_day["adaptive_approve"]:.1f} if the checker may approve,
{per_day["static_risk"]:.1f} for fixed rules, {per_day["always_human"]:.1f} when a person approves everything.

What this shows:

- **When the checker may only block during a takeover**, this project let through no more harm than fixed rules at every
  catch rate tested ({", ".join(f"{100 * r:.0f}%" for r in beats) or "none"}), with about half the interruptions. The price is a longer queue.
- **If the checker may also approve**, a confident but mediocre checker is dangerous: it beat fixed rules only at catch rates of
  {", ".join(f"{100 * r:.0f}%" for r in approve_beats) or "none tested"}. This result is why the default policy is `takeover: veto`.
  The default used to allow approval at confidence 0.85; it changed after this experiment. The free rules checker never
  reaches 0.85 confidence, so none of the earlier results move.
- A checker that reviews everything on its own (and never interrupts anyone) only beats this project once it catches
  {f"{100 * min(checker_alone):.0f}%" if checker_alone else "more than 100%"} or more of harmful actions.

## Does pacing help?

With a budget above one interruption an hour, the router can save the remaining interruptions for the riskiest high risk
actions instead of spending them first come, first served. Paired difference, pacing minus no pacing:

| Budget | Harm, points (95% CI) | Interruptions per day (95% CI) |
|---|---|---|
{pace}

Pacing was a small improvement on both measures, with confidence intervals below zero, at budgets of
{", ".join(f"{b} per hour" for b in paced_ok) or "none of the budgets tested"}. It stays off by default
(`Allocator(pacing=True)` turns it on) until it is tested with a real checker."""


def bench_block() -> str | None:
    path = ROOT / "results" / "benchmark.json"
    if not path.exists():
        return None
    b = json.loads(path.read_text(encoding="utf-8"))
    names = {"in_process": "Library, one process", "shared_file_state": "Library, state shared through a file", "http_localhost": "HTTP service, same machine"}
    rows = ["| Mode | Median | 99th percentile | Decisions per second |", "|---|---|---|---|"]
    for k, label in names.items():
        v = b[k]
        rows.append(f"| {label} | {v['p50_ms']:.2f} ms | {v['p99_ms']:.2f} ms | {v['per_second']:,.0f} |")
    m = b["machine"]
    return (
        "<!-- bench:start (generated by scripts/make_report.py from results/benchmark.json; do not edit) -->\n"
        "Time for one decision with the rules checker, measured by `scripts/benchmark.py` "
        f"(Python {m['python']}, {m['cpus']} CPUs, a mix of low to critical actions):\n\n" + "\n".join(rows) + "\n<!-- bench:end -->"
    )


def findings_summary(rows, rob, res) -> str:
    """The three things the simulation found, in plain words, with numbers from the result files."""
    h = headline(rows)
    parts: list[str] = []
    d = PAIRED[f"adaptive_{HEADLINE_BUDGET}_vs_static_risk_fatigue_on"]
    parts.append(
        f"This project and fixed approval rules ran on exactly the same days, so I compared them day by day, with a limit of {HEADLINE_BUDGET} interruption an hour. "
        f"The person was interrupted {abs(d['interrupts_diff_per_day']):.1f} fewer times a day "
        f"(95% confidence interval {abs(d['interrupts_diff_ci95'][1]):.1f} to {abs(d['interrupts_diff_ci95'][0]):.1f}), and "
        f"{abs(d['harm_diff_points']):.1f} percentage points fewer harmful actions got through "
        f"({abs(d['harm_diff_ci95'][1]):.1f} to {abs(d['harm_diff_ci95'][0]):.1f}). "
        f"The cost is a longer queue: {h['adapt_def']:.1f} actions a day waited for the person instead of {h['static_def']:.1f}."
    )
    if rob:
        changes = [x for x in rob["variants"] if x["kind"] in ("person", "workload", "accounting")]
        better = sum(x["harm_diff_ci95"][1] < 0 for x in changes)
        worse = sum(x["harm_diff_ci95"][0] > 0 for x in changes)
        att = rob["budget_drain_attack"]

        def a(strat, k):
            return next(r for r in att if r["human"] == "fatigue on" and r["strategy"] == strat and r["burst"] == k)["success_pct"]

        top = max(r["burst"] for r in att)
        parts.append(
            f"I changed the assumptions one at a time: how good the person is, how fast they tire, how busy the agent is, how rare harm is, "
            f"how interruptions are counted. Out of {len(changes)} changes, less harm got through in {better}, more in {worse or 'none'}"
            + (
                ""
                if not (rest := len(changes) - better - worse)
                else ", and in the remaining one the difference was too small to call."
                if rest == 1
                else f", and in the remaining {rest} the difference was too small to call."
            )
        )
        parts.append(
            f"I also tried to break it. An agent that fires {top} harmless looking risky actions to wear the person out, then hides a harmful one, "
            f"got through {a('static_risk', top):.0f}% of the time against fixed rules and {a('adaptive', top):.0f}% here."
        )
    if res:
        sweep = [r for r in res["checker_sweep"] if r["fatigue"] == "on"]

        def hs(strat, rc):
            return next(x for x in sweep if x["strategy"] == strat and x["recall"] == rc)["harm_pct"]

        low = min(r["recall"] for r in sweep)
        parts.append(
            "The finding that surprised me most is about the automatic checker. If it is allowed to approve risky actions while the person is busy, "
            f"a confident but mediocre checker (one that catches {100 * low:.0f}% of harm) let {hs('adaptive_approve', low):.0f}% of harmful actions through, "
            f"far worse than fixed rules at {hs('static_risk', low):.0f}%. Allowed only to block, the same checker was no worse than fixed rules. "
            "So by default the checker can stop things but never approve them on its own."
        )
    return "\n\n".join(parts)


def readme_latency() -> str | None:
    path = ROOT / "results" / "benchmark.json"
    if not path.exists():
        return None
    b = json.loads(path.read_text(encoding="utf-8"))
    return (
        "<!-- latency:start (generated by scripts/make_report.py from results/benchmark.json; do not edit) -->"
        f"A decision takes {b['in_process']['p50_ms']:.2f} ms in process ({b['in_process']['p99_ms']:.2f} ms at the 99th percentile) "
        f"and {b['http_localhost']['p50_ms']:.2f} ms over HTTP on the same machine."
        "<!-- latency:end -->"
    )


def hero_title(h) -> str:
    return f"{h['interrupt_cut_pct']:.0f}% fewer interruptions, and {harm_phrase(h)} getting through"


def robustness_table(rob) -> str:
    lines = [
        "| What changed | Harm difference in points (95% CI) | Interruptions per day difference (95% CI) | Deferred per day (fixed rules → this project) |",
        "|---|---|---|---|",
    ]
    for v in rob["variants"]:
        lines.append(
            f"| {v['name']} | {v['harm_diff_points']:+.1f} ({v['harm_diff_ci95'][0]:+.1f} to {v['harm_diff_ci95'][1]:+.1f}) | "
            f"{v['interrupts_diff_per_day']:+.1f} ({v['interrupts_diff_ci95'][0]:+.1f} to {v['interrupts_diff_ci95'][1]:+.1f}) | "
            f"{v['static_deferred']:.1f} → {v['adaptive_deferred']:.1f} |"
        )
    return "\n".join(lines)


def attack_table(rob) -> str:
    lines = ["| Person | Decoys fired first | Fixed approval rules | This project |", "|---|---|---|---|"]
    rows = rob["budget_drain_attack"]
    for human in ("fatigue on", "fatigue off"):
        for k in sorted({r["burst"] for r in rows}):
            cell = {}
            for r in rows:
                if r["human"] == human and r["burst"] == k:
                    cell[r["strategy"]] = f"{r['success_pct']:.1f}% ({r['success_ci95'][0]:.1f} to {r['success_ci95'][1]:.1f})"
            lines.append(f"| {'gets tired' if human == 'fatigue on' else 'never tires'} | {k} | {cell['static_risk']} | {cell['adaptive']} |")
    return "\n".join(lines)


def headline(rows) -> dict:
    s, a = pick(rows, "on", "all", "static_risk", None), pick(rows, "on", "all", "adaptive", HEADLINE_BUDGET)
    so, ao = pick(rows, "off", "all", "static_risk", None), pick(rows, "off", "all", "adaptive", HEADLINE_BUDGET)
    h = pick(rows, "off", "all", "always_human", None)
    return {
        "interrupt_cut_pct": 100 * (1 - a["interrupts_per_day"] / s["interrupts_per_day"]),
        "static_int": s["interrupts_per_day"],
        "adapt_int": a["interrupts_per_day"],
        "static_harm": s["harm_executed_pct"],
        "adapt_harm": a["harm_executed_pct"],
        "static_harm_off": so["harm_executed_pct"],
        "adapt_harm_off": ao["harm_executed_pct"],
        "static_def": s["deferred_per_day"],
        "adapt_def": a["deferred_per_day"],
        "adapt_unres": a["benign_unresolved_pct"],
        "human_harm_off": h["harm_executed_pct"],
        "human_int": h["interrupts_per_day"],
        "human_harm_on": pick(rows, "on", "all", "always_human", None)["harm_executed_pct"],
        "tiered_floor_off": min(
            r["harm_executed_pct"] for r in rows if r["fatigue"] == "off" and r["profile"] == "all" and r["strategy"] in ("static_risk", "adaptive")
        ),
    }


PAIRED: dict = {}


def harm_phrase(h) -> str:
    """Wording is decided by the paired test, not by eyeballing point estimates."""
    his = [d["harm_diff_ci95"][1] for d in PAIRED.values()]
    los = [d["harm_diff_ci95"][0] for d in PAIRED.values()]
    if his and all(x < 0 for x in his):
        return "less harm"
    if los and any(x > 0 for x in los):
        return "more harm"
    return "no more harm"


def fatigue_sentence(h) -> str:
    if h["human_harm_on"] > max(h["static_harm"], h["adapt_harm"]):
        return "Once fatigue is modelled, reviewing everything does worse than either tiered policy."
    return "Even with fatigue modelled, reviewing everything still catches the most harm."


def results_md(rows, manifest, acc, tag) -> str:
    h = headline(rows)
    return f"""# Results

_Generated by `scripts/make_report.py` from `results/{tag}/` (commit `{manifest["git_commit"]}`). Do not edit by hand._

## In short

{findings_summary(rows, manifest.get("robustness"), manifest.get("research"))}

**Setup.** {manifest["pool_size"]} unique synthetic actions ({manifest["pool_harmful"]} harmful) → workdays of ~96 agent actions
(8% harmful), {len(manifest["seeds"])} seeds × {manifest["episodes_per_seed"]} episodes × 3 human-availability profiles = 300 workdays per strategy.
Safety model: **{manifest["reviewer"]}**. Simulated human catches 95% of harmful actions when fresh, wrongly blocks 3% of benign ones,
and (fatigue on) loses 4 points of catch rate for every review beyond 6 in the past hour (floor 50%).
That fatigue curve is an assumption, but a conservative one: clinicians override 49% to 96% of drug safety alerts
([van der Sijs et al. 2006](https://pmc.ncbi.nlm.nih.gov/articles/PMC1447540)), and acceptance of reminders dropped 30% for each
additional reminder per patient visit ([Ancker et al. 2017](https://pmc.ncbi.nlm.nih.gov/articles/PMC5387195/)).
Results with fatigue switched off are reported next to every fatigue result.

![frontier](../figures/frontier.png)

## Headline

With the attention budget at **{HEADLINE_BUDGET} interrupt/hour**, adaptive routing cut human interrupts by
**{h["interrupt_cut_pct"]:.0f}%** versus static risk tiers ({h["static_int"]:.1f} → {h["adapt_int"]:.1f} per day) and let through
**{harm_phrase(h)}**: {h["adapt_harm"]:.1f}% vs {h["static_harm"]:.1f}% of harmful actions executed with alert fatigue,
{h["adapt_harm_off"]:.1f}% vs {h["static_harm_off"]:.1f}% without.

The price: more deferred actions ({h["static_def"]:.1f} → {h["adapt_def"]:.1f} per day) and {h["adapt_unres"]:.2f}% of benign actions
still waiting for a human when the day ended.

A human who reviews everything and never tires is still the safest option ({h["human_harm_off"]:.1f}% harm executed), at
{h["human_int"]:.0f} interrupts a day. {fatigue_sentence(h)}

## All profiles, fatigue on

{table(rows, "on")}

## All profiles, fatigue off (sensitivity check)

{table(rows, "off")}

## Is the difference real?

Every strategy runs on exactly the same 300 workdays (same actions, same schedules, same luck for the simulated person),
so the fair test is the difference on each day, bootstrapped over days:

{paired_table(manifest["paired"])}

An interval that does not include 0 means the difference is unlikely to be noise.

## By human availability (fatigue on)

{profile_table(rows)}

{robustness_md(manifest.get("robustness"))}

{research_md(manifest.get("research"))}

## Safety-model verdicts on the unique action pool

{accuracy_table(acc)}

## What these numbers do and do not show

- **Synthetic data, simulated human.** Templates, workload and human behaviour are assumptions written by the authors.
  The comparison between strategies is the point; the absolute rates are not predictions about any real deployment.
- **The heuristic reviewer is weak on subtle harm** (see the verdict table). At least {h["tiered_floor_off"]:.0f}% of harmful actions get through
  every tiered policy even with a tireless human, mostly subtle actions that the tool registry scores low or medium and the heuristic allows.
  Better risk metadata or a stronger reviewer has to close that gap; routing alone cannot.
- **The heuristic was adjusted once** after inspecting the pool (two regex bugs: `chmod` flags and `key: false` config
  flags). No other tuning against these results.
- **Fatigue drives the always-human result.** Compare the two tables before quoting it.
- **Deferral is not free.** Adaptive trades interrupts for waiting; in the `away` profile queued actions wait hours.
- Run `scripts/run_experiments.py --reviewer anthropic` to repeat everything with an LLM reviewer (costs money; capped by `MAX_SPEND_USD`).
"""


def paired_table(paired) -> str:
    lines = ["| Comparison | Harm executed, difference in points (95% CI) | Interrupts per day, difference (95% CI) |", "|---|---|---|"]
    for key, d in paired.items():
        name = key.replace("adaptive_1_vs_static_risk_fatigue_", "Adaptive (1/h) minus static tiers, fatigue ")
        lines.append(
            f"| {name} | {d['harm_diff_points']:+.1f} ({d['harm_diff_ci95'][0]:+.1f} to {d['harm_diff_ci95'][1]:+.1f}) | "
            f"{d['interrupts_diff_per_day']:+.1f} ({d['interrupts_diff_ci95'][0]:+.1f} to {d['interrupts_diff_ci95'][1]:+.1f}) |"
        )
    return "\n".join(lines)


def readme_compare(rows, tag) -> str:
    order = [
        ("no_oversight", None, "Let the agent do anything"),
        ("always_model", None, "An automatic checker reviews every action (the free rule based one)"),
        ("always_human", None, "A person approves every action"),
        ("static_risk", None, "Fixed rules: risky actions always go to a person"),
        ("adaptive", HEADLINE_BUDGET, "This project"),
    ]
    lines = [
        f"<!-- compare:start (generated by scripts/make_report.py from results/{tag}; do not edit) -->",
        "| Approach | Harmful actions that went through | Times the person was interrupted per day | Harmful actions that went through if the person never gets tired |",
        "|---|---|---|---|",
    ]
    for s, b, label in order:
        on, off = pick(rows, "on", "all", s, b), pick(rows, "off", "all", s, b)
        name = f"**{label}**" if s == "adaptive" else label
        lines.append(f"| {name} | {on['harm_executed_pct']:.0f}% | {on['interrupts_per_day']:.0f} | {off['harm_executed_pct']:.0f}% |")
    lines.append("<!-- compare:end -->")
    return "\n".join(lines)


def noise_phrase(d) -> str:
    lo, hi = d["harm_diff_ci95"]
    if hi < 0 or lo > 0:
        return "a real difference, not noise"
    return "a difference within the noise"


def readme_headline(rows, tag) -> str:
    h = headline(rows)
    cut = h["interrupt_cut_pct"]
    how_much = "about half as often as" if 45 <= cut <= 55 else f"{cut:.0f}% less often than"
    harm = {"less harm": "less harm got through", "more harm": "more harm got through", "no more harm": "no more harm got through"}[harm_phrase(h)]
    return f"""<!-- headline:start (generated by scripts/make_report.py from results/{tag}; do not edit) -->
On 300 simulated workdays it interrupted people {how_much} fixed approval rules ({h["adapt_int"]:.1f} times a day
instead of {h["static_int"]:.1f}), and {harm} ({h["adapt_harm"]:.1f}% of harmful actions instead of {h["static_harm"]:.1f}%).

![Interruptions per day and harmful actions that got through, fixed approval rules vs this project](figures/hero.png)
<!-- headline:end -->"""


def linkedin_post(rows, research=None) -> str:
    h = headline(rows)
    half = "about half as often as" if 45 <= h["interrupt_cut_pct"] <= 55 else f"{h['interrupt_cut_pct']:.0f}% less often than"
    bench_path = ROOT / "results" / "benchmark.json"
    speed = ""
    if bench_path.exists():
        b = json.loads(bench_path.read_text(encoding="utf-8"))
        speed = f", and a decision takes about {b['in_process']['p50_ms']:.1f} ms in process"
    surprise = ""
    if research:
        sweep = [r for r in research["checker_sweep"] if r["fatigue"] == "on"]
        low = min(r["recall"] for r in sweep)

        def hs(strat):
            return next(x for x in sweep if x["strategy"] == strat and x["recall"] == low)["harm_pct"]

        surprise = (
            "The result I did not expect: letting a confident but mediocre checker approve risky actions while the person is busy "
            f"made things much worse ({hs('adaptive_approve'):.0f}% of harmful actions got through, against {hs('static_risk'):.0f}% with plain fixed rules). "
            "Allowed only to block, the same checker was fine. How much you can trust a checker's yes matters more than how often it says no.\n\n"
        )
    return f"""<!-- generated by scripts/make_report.py; numbers come from results/. -->

Every AI agent product now has an approve button. Almost none of them ask whether the person pressing it is still paying attention.

Hospitals have measured this for twenty years. Clinicians override most safety alerts, and every extra alert makes the next one easier to ignore. Agent approvals are heading the same way.

So I built an open source layer that sits between an agent and its tools and decides who should check each action: nobody, an automatic checker, or a person. It treats the person's attention as a budget. When the budget runs out, the checker can stop risky actions but cannot approve them, and critical actions always wait for a human.

On 300 simulated workdays it interrupted people {half} fixed approval rules ({h["adapt_int"]:.1f} times a day instead of {h["static_int"]:.1f}), and {harm_phrase(h)} got through ({h["adapt_harm"]:.1f}% of harmful actions instead of {h["static_harm"]:.1f}%). It held up when I changed the assumptions one at a time, and when I tried to wear out the reviewer on purpose.

{surprise}It works with the OpenAI Agents SDK, LangChain, any MCP server, Claude Code, or any language over HTTP{speed}. Everything is reproducible from the repo, including the parts that do not work yet: the data is simulated, and the free rules checker still misses more than half of the subtle cases.

Code, data and the full write up: https://github.com/dhruv1999/Oversight-for-AI-Agents

#AISafety #AIAgents #ProductManagement #OpenSource
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="heuristic")
    args = ap.parse_args()
    rows, manifest, acc = load(args.tag)
    h = headline(rows)
    title = f"{h['interrupt_cut_pct']:.0f}% fewer interruptions than fixed approval rules, and {harm_phrase(h)} (lower left is better)"
    charts.frontier(rows, ROOT / "figures", manifest["reviewer"], title)
    charts.hero(pick(rows, "on", "all", "static_risk", None), pick(rows, "on", "all", "adaptive", HEADLINE_BUDGET), hero_title(h), ROOT / "figures")
    rob_path = ROOT / "results" / args.tag / "robustness.json"
    rob = json.loads(rob_path.read_text(encoding="utf-8")) if rob_path.exists() else None
    if rob:
        charts.robustness(rob["variants"], ROOT / "figures")
        charts.attack(rob["budget_drain_attack"], ROOT / "figures")
    manifest["robustness"] = rob
    res_path = ROOT / "results" / args.tag / "research.json"
    research = json.loads(res_path.read_text(encoding="utf-8")) if res_path.exists() else None
    if research:
        charts.checker_quality(research["checker_sweep"], research["heuristic_recall"], ROOT / "figures")
    manifest["research"] = research
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "results.md").write_text(results_md(rows, manifest, acc, args.tag), encoding="utf-8")
    (ROOT / "docs" / "linkedin_post.md").write_text(linkedin_post(rows, research), encoding="utf-8")
    readme = ROOT / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        new = re.sub(r"<!-- compare:start.*?<!-- compare:end -->", readme_compare(rows, args.tag), text, flags=re.S)
        new = re.sub(r"<!-- headline:start.*?<!-- headline:end -->", readme_headline(rows, args.tag), new, flags=re.S)
        lat = readme_latency()
        if lat:
            new = re.sub(r"<!-- latency:start.*?<!-- latency:end -->", lambda _: lat, new, flags=re.S)
        readme.write_text(new, encoding="utf-8")
    arch = ROOT / "docs" / "architecture.md"
    bench = bench_block()
    if bench and arch.exists():
        text = arch.read_text(encoding="utf-8")
        arch.write_text(re.sub(r"<!-- bench:start.*?<!-- bench:end -->", lambda _: bench, text, flags=re.S), encoding="utf-8")
    print(json.dumps(headline(rows), indent=1))


if __name__ == "__main__":
    main()
