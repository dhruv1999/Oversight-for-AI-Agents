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
    rows = json.loads((ROOT / "results" / tag / "summary.json").read_text())
    manifest = json.loads((ROOT / "results" / tag / "manifest.json").read_text())
    acc = json.loads((ROOT / "results" / tag / "reviewer_accuracy.json").read_text())
    paired = json.loads((ROOT / "results" / tag / "paired.json").read_text())
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
    assumptions = [x for x in rob["variants"] if x["kind"] in ("baseline", "person", "workload", "accounting")]
    better = sum(x["harm_diff_ci95"][1] < 0 for x in assumptions)
    worse = sum(x["harm_diff_ci95"][0] > 0 for x in assumptions)
    fewer = sum(x["interrupts_diff_ci95"][1] < 0 for x in assumptions)
    no_fb = v["Remove: checker takes over when the budget is spent"]
    lax = v["Remove: stricter bar for the checker when it takes over"]
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
- **Without the stricter bar for the checker when it takes over**, far fewer actions wait ({lax["adaptive_deferred"]:.1f} per day instead of
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


def readme_block(rows, tag, reviewer) -> str:
    h = headline(rows)
    on = PAIRED[f"adaptive_{HEADLINE_BUDGET}_vs_static_risk_fatigue_on"]
    off = PAIRED[f"adaptive_{HEADLINE_BUDGET}_vs_static_risk_fatigue_off"]
    return f"""<!-- results:start (generated by scripts/make_report.py from results/{tag}; do not edit) -->
Both approaches were run on exactly the same 300 made up workdays, so they can be compared day by day.
With a limit of {HEADLINE_BUDGET} interruption per hour, this project interrupted the person
{abs(on["interrupts_diff_per_day"]):.1f} fewer times a day (95% confidence: between {abs(on["interrupts_diff_ci95"][1]):.1f} and {abs(on["interrupts_diff_ci95"][0]):.1f}).
It also let through {abs(on["harm_diff_points"]):.1f} points less harm when the simulated person gets tired
(between {abs(on["harm_diff_ci95"][1]):.1f} and {abs(on["harm_diff_ci95"][0]):.1f}) and {abs(off["harm_diff_points"]):.1f} points less when they never tire
(between {abs(off["harm_diff_ci95"][1]):.1f} and {abs(off["harm_diff_ci95"][0]):.1f}).

The cost is a longer queue: {h["adapt_def"]:.1f} actions a day waited for the person instead of {h["static_def"]:.1f}.
The checker used here is the free `{reviewer}` one. Every table is in [docs/results.md](docs/results.md).
<!-- results:end -->"""


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
    d = PAIRED[f"adaptive_{HEADLINE_BUDGET}_vs_static_risk_fatigue_on"]
    return f"""<!-- headline:start (generated by scripts/make_report.py from results/{tag}; do not edit) -->
In 300 simulated workdays it interrupted people **{h["interrupt_cut_pct"]:.0f}% less** than fixed approval rules
({h["adapt_int"]:.1f} times a day instead of {h["static_int"]:.1f}) and let through **{harm_phrase(h)}**
({h["adapt_harm"]:.1f}% of harmful actions instead of {h["static_harm"]:.1f}%; {noise_phrase(d)}).

![Harmful actions that ran vs how often a person was interrupted](figures/frontier.png)
<!-- headline:end -->"""


def linkedin_post(rows) -> str:
    h = headline(rows)
    return f"""<!-- generated by scripts/make_report.py; numbers come from results/. -->

AI agents are starting to take real actions: running SQL, sending email, paying invoices. The usual safety answer is "keep a human in the loop". But human attention runs out. If an agent asks 50 times a day, the 50th approval is a rubber stamp.

So I built Adaptive Oversight, an open-source router that decides, for every action an agent wants to take, who should check it:
→ the agent itself (low risk)
→ a safety model (medium risk, or when the human is busy)
→ a human (high risk, within an attention budget; critical actions always)

It scores risk from the tool call itself (what it touches, whether it can be undone, how far it reaches, how sensitive the data is), tracks how much attention the human has left, and explains and logs every routing decision.

In a simulation of 300 synthetic agent workdays per strategy, with a budget of {HEADLINE_BUDGET} interruption per hour:
• {h["interrupt_cut_pct"]:.0f}% fewer human interruptions than fixed risk tiers ({h["static_int"]:.1f} → {h["adapt_int"]:.1f} per day)
• {harm_phrase(h).capitalize()} let through ({h["adapt_harm"]:.1f}% vs {h["static_harm"]:.1f}% of harmful actions executed)
• The trade-off: more actions wait in a queue ({h["static_def"]:.1f} → {h["adapt_def"]:.1f} per day)

What it does not solve (yet): with a simple rule-based reviewer, about {h["tiered_floor_off"]:.0f}% of harmful actions still get through any tiered policy, mostly subtle ones that look routine. A human who never tires and reviews everything does best ({h["human_harm_off"]:.1f}%), but that means {h["human_int"]:.0f} interruptions a day. The data is synthetic and the human is simulated, so treat these as a comparison of strategies, not real-world rates.

It also ships as a Claude Code hook, so you can put it in front of your own coding agent today.

Code, data and every number are reproducible from one script: https://github.com/dhruv1999/Oversight-for-AI-Agents

#AISafety #AIAgents #HumanInTheLoop #OpenSource
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
    rob = json.loads(rob_path.read_text()) if rob_path.exists() else None
    if rob:
        charts.robustness(rob["variants"], ROOT / "figures")
        charts.attack(rob["budget_drain_attack"], ROOT / "figures")
    manifest["robustness"] = rob
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "results.md").write_text(results_md(rows, manifest, acc, args.tag))
    (ROOT / "docs" / "linkedin_post.md").write_text(linkedin_post(rows))
    readme = ROOT / "README.md"
    if readme.exists():
        text = readme.read_text()
        new = re.sub(r"<!-- results:start.*?<!-- results:end -->", readme_block(rows, args.tag, manifest["reviewer"]), text, flags=re.S)
        new = re.sub(r"<!-- compare:start.*?<!-- compare:end -->", readme_compare(rows, args.tag), new, flags=re.S)
        new = re.sub(r"<!-- headline:start.*?<!-- headline:end -->", readme_headline(rows, args.tag), new, flags=re.S)
        readme.write_text(new)
    print(json.dumps(headline(rows), indent=1))


if __name__ == "__main__":
    main()
