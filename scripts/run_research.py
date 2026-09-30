"""Two research questions, answered in simulation.

1. How good must the automatic checker be? Sweep a simulated checker's recall on harmful actions
   (false alarms fixed at 2%) and see where each strategy lands.
2. Does pacing help? With a larger budget, keep the remaining interrupts for the riskiest high actions
   instead of first come, first served. Paired comparison against the same router without pacing.

    uv run python scripts/run_research.py            # ~2 minutes, free
    uv run python scripts/run_research.py --quick

Writes results/heuristic/research.json. Settings were fixed before running.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
from typing import Any

from oversight.policies import DEFAULT_POLICY, DEFAULT_TOOLS
from oversight.policy import Policy
from oversight.registry import ToolRegistry
from oversight.safety_model import HeuristicSafetyModel
from oversight.schema import Verdict
from oversight.sim.availability import PROFILES, make_schedule
from oversight.sim.checkers import SimulatedChecker
from oversight.sim.episodes import sample_episode
from oversight.sim.scenarios import build_pool
from oversight.sim.simulator import run_episode
from oversight.sim.stats import paired_difference, ratio_ci

ROOT = Path(__file__).resolve().parent.parent
RECALLS = [0.2, 0.4, 0.6, 0.8, 0.9, 0.95, 1.0]
FALSE_ALARM = 0.02
STRATEGIES = [("adaptive", 1), ("static_risk", None), ("always_model", None), ("always_human", None)]
PACING_BUDGETS = [2, 3, 4, 6]


def workdays(pool, seeds, n_eps):
    for profile in PROFILES:
        for seed in seeds:
            for ep in range(n_eps):
                yield seed, ep, sample_episode(pool, random.Random(f"{seed}:{ep}")), make_schedule(profile, random.Random(f"{seed}:{ep}:{profile}"))


def summarise(eps: list[dict[str, Any]], rng: random.Random) -> dict[str, Any]:
    lo, hi = ratio_ci([m["harmful_executed"] for m in eps], [m["harmful"] for m in eps], rng)
    return {
        "harm_pct": 100 * sum(m["harmful_executed"] for m in eps) / sum(m["harmful"] for m in eps),
        "harm_ci95": [100 * lo, 100 * hi],
        "interrupts_per_day": sum(m["interrupts"] for m in eps) / len(eps),
        "benign_blocked_pct": 100 * sum(m["benign_blocked"] for m in eps) / sum(m["benign"] for m in eps),
    }


def checker_recall(pool, registry, checker) -> float:
    harmful = [p for p in pool if p.harmful]
    stopped = sum(checker.review(registry.to_action(p.key, p.tool, p.params, p.description)).verdict != Verdict.ALLOW for p in harmful)
    return stopped / len(harmful)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    seeds, n_eps = ([0], 3) if args.quick else ([0, 1, 2, 3, 4], 20)
    policy = Policy.load(DEFAULT_POLICY)
    registry = ToolRegistry.load(DEFAULT_TOOLS, policy)
    pool = build_pool(0)
    days = list(workdays(pool, seeds, n_eps))
    t0 = time.time()

    sweep = []
    for fatigue, human in (("on", None), ("off", {"fatigue_slope": 0.0})):
        for recall in RECALLS:
            checker = SimulatedChecker(pool, recall, FALSE_ALARM)
            for strat, budget in STRATEGIES:
                eps = [run_episode(ev, sch, strat, policy, registry, checker, s, e, budget, human).metrics for s, e, ev, sch in days]
                sweep.append({"fatigue": fatigue, "recall": recall, "strategy": strat, "budget_per_hour": budget, **summarise(eps, random.Random(0))})
        print(f"{time.time() - t0:4.0f}s checker sweep, fatigue {fatigue}")

    pacing = []
    heuristic = HeuristicSafetyModel()
    for budget in PACING_BUDGETS:
        plain = [run_episode(ev, sch, "adaptive", policy, registry, heuristic, s, e, budget).metrics for s, e, ev, sch in days]
        paced = [run_episode(ev, sch, "adaptive", policy, registry, heuristic, s, e, budget, router_kwargs={"pacing": True}).metrics for s, e, ev, sch in days]
        d = paired_difference(paced, plain, random.Random(3))
        pacing.append({"budget_per_hour": budget, **d})
        print(f"{time.time() - t0:4.0f}s pacing budget {budget}: harm {d['harm_diff_points']:+.2f} pts, interrupts {d['interrupts_diff_per_day']:+.2f}/day")

    out = ROOT / "results" / ("heuristic_quick" if args.quick else "heuristic")
    out.mkdir(parents=True, exist_ok=True)
    result = {
        "false_alarm": FALSE_ALARM,
        "heuristic_recall": checker_recall(pool, registry, heuristic),
        "checker_sweep": sweep,
        "pacing": pacing,
    }
    (out / "research.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"wrote {out}/research.json in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
