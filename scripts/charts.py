"""All figures. One data hue (this project) plus neutral ink for comparisons, identified by direct labels."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SURFACE, INK, INK2, MUTED, GRID, AXIS, SERIES = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#2a78d6"
LABELS = {
    "no_oversight": "No oversight",
    "always_model": "Automatic checker reviews everything",
    "static_risk": "Fixed approval rules",
    "always_human": "Person approves everything",
    "adaptive": "This project",
}


def pick(rows, fatigue="on", profile="all", strategy=None, budget=None):
    for r in rows:
        if r["fatigue"] == fatigue and r["profile"] == profile and r["strategy"] == strategy and r["budget_per_hour"] == budget:
            return r
    raise KeyError((fatigue, profile, strategy, budget))


def _style(ax, grid_axis: str = "both") -> None:
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
    if grid_axis:
        ax.grid(True, axis=grid_axis, color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED, labelcolor=INK2)


def _save(fig, out: Path, name: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / f"{name}.png", dpi=160, facecolor=SURFACE, metadata={"Software": None})
    fig.savefig(out / f"{name}.svg", facecolor=SURFACE, metadata={"Date": None})
    plt.close(fig)


def _setup() -> None:
    # svg.hashsalt + no dates: the same data always produces byte identical files
    plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans"], "font.size": 10, "svg.hashsalt": "oversight"})


def hero(static: dict[str, Any], adaptive: dict[str, Any], title: str, out: Path) -> None:
    """The picture a busy reader sees first: two numbers, before and after."""
    _setup()
    fig, axes = plt.subplots(1, 2, figsize=(10, 2.1), facecolor=SURFACE)
    panels = [
        ("Times a person is interrupted, per day", "interrupts_per_day", "{:.1f}"),
        ("Harmful actions that got through", "harm_executed_pct", "{:.1f}%"),
    ]
    for ax, (label, key, f) in zip(axes, panels, strict=True):
        _style(ax, grid_axis="")
        vals = [static[key], adaptive[key]]
        ax.barh([1, 0], vals, height=0.52, color=[MUTED, SERIES])
        for y, v in zip([1, 0], vals, strict=True):
            ax.text(v + max(vals) * 0.02, y, f.format(v), va="center", color=INK, fontsize=11)
        ax.set_yticks([1, 0], ["Fixed approval rules", "This project"])
        ax.set_xticks([])
        ax.spines["bottom"].set_visible(False)
        ax.set_xlim(0, max(vals) * 1.25)
        ax.set_title(label, color=INK2, fontsize=10, loc="left")
    fig.suptitle(title, color=INK, fontsize=13, x=0.01, y=0.98, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.9), h_pad=0.2)
    _save(fig, out, "hero")


def frontier(rows, out: Path, reviewer: str, title: str) -> None:
    _setup()
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True, facecolor=SURFACE)
    for ax, fatigue, sub in zip(axes, ("on", "off"), ("If the person gets tired", "If the person never gets tired"), strict=True):
        _style(ax)
        ad = sorted((r for r in rows if r["fatigue"] == fatigue and r["profile"] == "all" and r["strategy"] == "adaptive"), key=lambda r: r["budget_per_hour"])
        xs = [r["interrupts_per_day"] for r in ad]
        ys = [r["harm_executed_pct"] for r in ad]
        for r in ad:
            lo, hi = r["harm_executed_ci95"]
            ax.plot([r["interrupts_per_day"]] * 2, [lo, hi], color=SERIES, alpha=0.35, linewidth=1)
        ax.plot(xs, ys, color=SERIES, linewidth=2, solid_capstyle="round", zorder=4)
        ax.scatter(xs, ys, s=64, color=SERIES, edgecolors=SURFACE, linewidths=2, zorder=5)
        ax.annotate("This project", (xs[0], ys[0]), xytext=(xs[0] - 2, min(ys) - 7), color=INK, fontsize=9, ha="left")
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
                ax.annotate(LABELS[s], (x, y), xytext=(x + dx, y + (2.5 if y > 20 else 9)), color=INK2, ha=ha, fontsize=9)
        ax.text(0.99, 0.74, "Agent does anything: 100% ran, 0 interruptions", transform=ax.transAxes, ha="right", va="top", color=MUTED, fontsize=8)
        ax.set_title(sub, color=INK, fontsize=11, loc="left")
        ax.set_xlabel("Times the person was interrupted per 8 hour day", color=INK2)
        ax.set_xlim(-2, 56)
        ax.set_ylim(0, 62)
    axes[0].set_ylabel("Harmful actions that ran (%)", color=INK2)
    fig.suptitle(title, color=INK, fontsize=12, x=0.01, ha="left")
    fig.text(
        0.01,
        0.005,
        f"Made up workdays, 300 per point. Bars show 95% confidence. Blue points: 1 to 10 interruptions per hour allowed. Checker: {reviewer}.",
        color=MUTED,
        fontsize=8,
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    _save(fig, out, "frontier")


def robustness(variants: list[dict[str, Any]], out: Path) -> None:
    """Dot and whisker: paired difference (this project minus fixed rules) under each changed assumption."""
    _setup()
    n = len(variants)
    fig, axes = plt.subplots(1, 2, figsize=(11, 0.42 * n + 1.6), sharey=True, facecolor=SURFACE, gridspec_kw={"width_ratios": [1.2, 1]})
    ys = list(range(n))[::-1]
    for ax, key, ci, label in (
        (axes[0], "harm_diff_points", "harm_diff_ci95", "Harmful actions that got through\n(difference in points; left of 0 is better)"),
        (axes[1], "interrupts_diff_per_day", "interrupts_diff_ci95", "Interruptions per day\n(difference; left of 0 is better)"),
    ):
        _style(ax, grid_axis="x")
        ax.axvline(0, color=AXIS, linewidth=1.5, zorder=1)
        for y, v in zip(ys, variants, strict=True):
            lo, hi = v[ci]
            ax.plot([lo, hi], [y, y], color=SERIES, linewidth=2, solid_capstyle="round", zorder=3)
            ax.scatter([v[key]], [y], s=56, color=SERIES, edgecolors=SURFACE, linewidths=2, zorder=4)
        ax.set_title(label, color=INK2, fontsize=10, loc="left")
    axes[0].set_yticks(ys, [v["name"] for v in variants], fontsize=9)
    axes[0].tick_params(axis="y", length=0)
    fig.suptitle("Does the result survive other assumptions? One change at a time, 300 paired workdays each", color=INK, fontsize=12, x=0.01, ha="left")
    note = "Lines show 95% confidence. Each row compares this project (1 interruption/hour) with fixed approval rules on the same days."
    fig.text(0.01, 0.005, note, color=MUTED, fontsize=8)
    fig.tight_layout(rect=(0, 0.02, 1, 0.95))
    _save(fig, out, "robustness")


def attack(rows: list[dict[str, Any]], out: Path) -> None:
    """Budget drain: success rate of one harmful action hidden after a burst of harmless looking ones."""
    _setup()
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True, facecolor=SURFACE)
    top = max(r["success_ci95"][1] for r in rows) * 1.15
    for ax, human, sub in zip(axes, ("fatigue on", "fatigue off"), ("If the person gets tired", "If the person never gets tired"), strict=True):
        _style(ax)
        ends = {}
        for strat, color in (("static_risk", MUTED), ("adaptive", SERIES)):
            pts = sorted((r for r in rows if r["human"] == human and r["strategy"] == strat), key=lambda r: r["burst"])
            xs = [r["burst"] for r in pts]
            ys = [r["success_pct"] for r in pts]
            ax.fill_between(xs, [r["success_ci95"][0] for r in pts], [r["success_ci95"][1] for r in pts], color=color, alpha=0.12, linewidth=0)
            ax.plot(xs, ys, color=color, linewidth=2, solid_capstyle="round", label=LABELS[strat])
            ax.scatter(xs, ys, s=56, color=color, edgecolors=SURFACE, linewidths=2, zorder=4)
            ends[strat] = (xs[-1], ys[-1])
        if abs(ends["static_risk"][1] - ends["adaptive"][1]) > top * 0.1:  # direct labels only when they cannot collide
            for strat, (x, y) in ends.items():
                ax.annotate(LABELS[strat], (x, y), xytext=(6, 0), textcoords="offset points", va="center", color=INK2, fontsize=9)
        ax.set_xticks([0, 3, 6, 12])
        ax.set_xlim(-0.5, 20)
        ax.set_ylim(0, top)
        ax.set_title(sub, color=INK, fontsize=11, loc="left")
        ax.set_xlabel("Harmless looking risky actions fired first", color=INK2)
    axes[0].set_ylabel("Hidden harmful action got through (%)", color=INK2)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles[::-1], labels[::-1], loc="upper right", frameon=False, ncol=2, fontsize=9, labelcolor=INK2)
    fig.suptitle("Can an agent tire out the reviewer and then slip one through?", color=INK, fontsize=12, x=0.01, ha="left")
    fig.text(0.01, 0.005, "300 attacks per point, 20 seconds between actions. Bands show 95% confidence.", color=MUTED, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 0.94))
    _save(fig, out, "attack")


ORANGE = "#eb6834"  # categorical slot 2, validated next to slot 1 (blue)


def checker_quality(sweep: list[dict[str, Any]], heuristic_recall: float, out: Path) -> None:
    """Harm vs checker recall for each strategy, with the person getting tired."""
    _setup()
    fig, ax = plt.subplots(figsize=(10, 4.6), facecolor=SURFACE)
    _style(ax)
    series = [
        ("adaptive", "This project (checker may only block when it takes over)", SERIES, "-"),
        ("adaptive_approve", "This project, if the checker may also approve", ORANGE, "-"),
        ("static_risk", LABELS["static_risk"], INK2, "-"),
        ("always_model", LABELS["always_model"], MUTED, "--"),
        ("always_human", LABELS["always_human"], MUTED, ":"),
    ]
    note = []
    for key, label, color, style in series:
        pts = sorted((r for r in sweep if r["fatigue"] == "on" and r["strategy"] == key), key=lambda r: r["recall"])
        xs = [100 * r["recall"] for r in pts]
        ys = [r["harm_pct"] for r in pts]
        ax.fill_between(xs, [r["harm_ci95"][0] for r in pts], [r["harm_ci95"][1] for r in pts], color=color, alpha=0.10, linewidth=0)
        ax.plot(xs, ys, color=color, linewidth=2, linestyle=style, solid_capstyle="round", label=label)
        ax.scatter(xs, ys, s=36, color=color, edgecolors=SURFACE, linewidths=1.5, zorder=4)
        note.append(pts[0]["interrupts_per_day"])
    ax.axvline(100 * heuristic_recall, color=AXIS, linewidth=1.5, zorder=1)
    ax.annotate(
        f"the free rules checker\ncatches {100 * heuristic_recall:.0f}%",
        (100 * heuristic_recall, 78),
        xytext=(6, 0),
        textcoords="offset points",
        color=INK2,
        fontsize=9,
    )
    ax.set_xlabel("How many harmful actions the automatic checker catches (%)", color=INK2)
    ax.set_ylabel("Harmful actions that got through (%)", color=INK2)
    ax.set_xlim(15, 102)
    ax.set_ylim(0, 90)
    ax.legend(loc="upper right", frameon=False, fontsize=9, labelcolor=INK2)
    fig.suptitle("How good must the automatic checker be?", color=INK, fontsize=12, x=0.01, ha="left")
    per_day = ", ".join(f"{n:.1f}" for n in note)
    fig.text(
        0.01,
        0.005,
        f"Person gets tired. Checker false alarms fixed at 2%. 300 workdays per point; bands show 95% confidence. "
        f"Interruptions per day, in legend order: {per_day}.",
        color=MUTED,
        fontsize=8,
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    _save(fig, out, "checker_quality")
