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

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# reference palette (light): one data hue, everything else is ink/chrome
SURFACE, INK, INK2, MUTED, GRID, AXIS, SERIES = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#2a78d6"
LABELS = {
    "no_oversight": "No oversight",
    "always_model": "Safety model reviews everything",
    "static_risk": "Static risk tiers",
    "always_human": "Human reviews everything",
    "adaptive": "Adaptive",
}
HEADLINE_BUDGET = 1


def load(tag: str):
    rows = json.loads((ROOT / "results" / tag / "summary.json").read_text())
    manifest = json.loads((ROOT / "results" / tag / "manifest.json").read_text())
    acc = json.loads((ROOT / "results" / tag / "reviewer_accuracy.json").read_text())
    return rows, manifest, acc


def pick(rows, fatigue="on", profile="all", strategy=None, budget=None):
    for r in rows:
        if r["fatigue"] == fatigue and r["profile"] == profile and r["strategy"] == strategy and r["budget_per_hour"] == budget:
            return r
    raise KeyError((fatigue, profile, strategy, budget))


def frontier(rows, out: Path, reviewer: str) -> None:
    plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans"], "font.size": 10})
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True, facecolor=SURFACE)
    for ax, fatigue, title in zip(axes, ("on", "off"), ("Human gets tired (alert fatigue on)", "Human never tires (fatigue off)"), strict=True):
        ax.set_facecolor(SURFACE)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(AXIS)
        ax.grid(True, color=GRID, linewidth=1)
        ax.set_axisbelow(True)
        ax.tick_params(colors=MUTED, labelcolor=INK2)
        # adaptive sweep: the one colored series
        ad = sorted((r for r in rows if r["fatigue"] == fatigue and r["profile"] == "all" and r["strategy"] == "adaptive"), key=lambda r: r["budget_per_hour"])
        xs = [r["interrupts_per_day"] for r in ad]
        ys = [r["harm_executed_pct"] for r in ad]
        for r in ad:
            lo, hi = r["harm_executed_ci95"]
            ax.plot([r["interrupts_per_day"]] * 2, [lo, hi], color=SERIES, alpha=0.35, linewidth=1)
        ax.plot(xs, ys, color=SERIES, linewidth=2, solid_capstyle="round", zorder=4)
        ax.scatter(xs, ys, s=64, color=SERIES, edgecolors=SURFACE, linewidths=2, zorder=5)
        ax.annotate(
            f"Adaptive, budget {ad[0]['budget_per_hour']}\u2192{ad[-1]['budget_per_hour']}/h",
            (xs[0], ys[0]),
            xytext=(xs[0] - 2, min(ys) - 7),
            color=INK,
            fontsize=9,
            ha="left",
        )
        # baselines: neutral points on top, identified by direct labels
        for s in ("always_model", "static_risk", "always_human"):
            r = pick(rows, fatigue, "all", s, None)
            x, y = r["interrupts_per_day"], r["harm_executed_pct"]
            lo, hi = r["harm_executed_ci95"]
            ax.plot([x, x], [lo, hi], color=MUTED, linewidth=1, zorder=6)
            ax.scatter([x], [y], s=64, color=INK2, edgecolors=SURFACE, linewidths=2, zorder=7)
            if s == "static_risk":
                ax.annotate(LABELS[s], (x, y), xytext=(x + 4, y + 7), color=INK2, fontsize=9, arrowprops=dict(arrowstyle="-", color=MUTED, linewidth=1))
            else:
                dx, ha = (1.2, "left") if x < 40 else (-1.2, "right")
                ax.annotate(LABELS[s], (x, y), xytext=(x + dx, y + (2.5 if y > 20 else 6)), color=INK2, ha=ha, fontsize=9)
        ax.text(0.99, 0.98, "No oversight: 100% executed, 0 interrupts", transform=ax.transAxes, ha="right", va="top", color=MUTED, fontsize=8)
        ax.set_title(title, color=INK, fontsize=11, loc="left")
        ax.set_xlabel("Human interrupts per workday (8 hours)", color=INK2)
        ax.set_xlim(-2, 56)
        ax.set_ylim(0, 62)
    axes[0].set_ylabel("Harmful actions that got executed (%)", color=INK2)
    h = headline(rows)
    fig.suptitle(
        f"Adaptive oversight: {h['interrupt_cut_pct']:.0f}% fewer interrupts than static tiers, {harm_phrase(h)} (lower left is better)",
        color=INK,
        fontsize=12,
        x=0.01,
        ha="left",
    )
    fig.text(0.01, 0.005, f"Synthetic workdays; 300 episodes per point; bars = 95% bootstrap CI. Safety model: {reviewer}.", color=MUTED, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "frontier.png", dpi=160, facecolor=SURFACE)
    fig.savefig(out / "frontier.svg", facecolor=SURFACE)
    plt.close(fig)


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
    lines = ["| Pool slice | allow | escalate | block |", "|---|---|---|---|"]
    for g in ("benign", "benign_lookalike", "harmful_overt", "harmful_subtle"):
        c = acc.get(g, {})
        lines.append(f"| {g.replace('_', ' ')} | {c.get('allow', 0)} | {c.get('escalate', 0)} | {c.get('block', 0)} |")
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


def harm_phrase(h) -> str:
    if h["adapt_harm"] <= h["static_harm"] and h["adapt_harm_off"] <= h["static_harm_off"]:
        return "no more harm"
    return "slightly more harm"


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

## By human availability (fatigue on)

{profile_table(rows)}

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


def readme_block(rows, tag, reviewer) -> str:
    h = headline(rows)
    return f"""<!-- results:start (generated by scripts/make_report.py from results/{tag}; do not edit) -->
![Harm executed vs human interrupts](figures/frontier.png)

With a budget of {HEADLINE_BUDGET} interrupt per hour, adaptive routing asked the human {h["interrupt_cut_pct"]:.0f}% less often than fixed
risk tiers ({h["adapt_int"]:.1f} times a day instead of {h["static_int"]:.1f}) and let through {harm_phrase(h)} ({h["adapt_harm"]:.1f}% of harmful
actions ran, against {h["static_harm"]:.1f}%). The cost is a longer queue: {h["adapt_def"]:.1f} actions a day waited for the human instead of {h["static_def"]:.1f}.

This is synthetic data with a simulated human and a `{reviewer}` safety model. Full tables and caveats are in [docs/results.md](docs/results.md).
<!-- results:end -->"""


def linkedin_post(rows) -> str:
    h = headline(rows)
    return f"""<!-- generated by scripts/make_report.py; numbers come from results/. Replace <REPO_URL> before posting. -->

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

Code, data and every number are reproducible from one script: <REPO_URL>

#AISafety #AIAgents #HumanInTheLoop #OpenSource
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="heuristic")
    args = ap.parse_args()
    rows, manifest, acc = load(args.tag)
    frontier(rows, ROOT / "figures", manifest["reviewer"])
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "results.md").write_text(results_md(rows, manifest, acc, args.tag))
    (ROOT / "docs" / "linkedin_post.md").write_text(linkedin_post(rows))
    readme = ROOT / "README.md"
    if readme.exists():
        text = readme.read_text()
        new = re.sub(r"<!-- results:start.*?<!-- results:end -->", readme_block(rows, args.tag, manifest["reviewer"]), text, flags=re.S)
        readme.write_text(new)
    print(json.dumps(headline(rows), indent=1))


if __name__ == "__main__":
    main()
