"""Reproduce every number in the README.

    uv run python scripts/run_experiments.py                      # heuristic reviewer, free, ~1-2 min
    uv run python scripts/run_experiments.py --quick              # smoke run
    uv run python scripts/run_experiments.py --reviewer anthropic --estimate   # print cost, spend nothing
    MAX_SPEND_USD=5 uv run python scripts/run_experiments.py --reviewer anthropic

Settings below were fixed before the comparative results were looked at.
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
import random
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from oversight.cache import ResponseCache  # noqa: E402
from oversight.policy import Policy  # noqa: E402
from oversight.pricing import cost_usd  # noqa: E402
from oversight.registry import ToolRegistry  # noqa: E402
from oversight.safety_model import SYSTEM_PROMPT, VERDICT_SCHEMA, HeuristicSafetyModel, LLMSafetyModel, build_user_prompt  # noqa: E402
from oversight.sim.availability import PROFILES, make_schedule  # noqa: E402
from oversight.sim.episodes import sample_episode  # noqa: E402
from oversight.sim.scenarios import build_pool  # noqa: E402
from oversight.sim.simulator import run_episode  # noqa: E402
from oversight.spend import SpendLimitExceeded, SpendTracker  # noqa: E402

SEEDS = [0, 1, 2, 3, 4]
EPISODES_PER_SEED = 20
BASELINES = ["no_oversight", "always_model", "static_risk", "always_human"]
BUDGETS_PER_HOUR = [1, 2, 3, 4, 6, 10]  # adaptive sweep; 6/h is the default policy
DEFAULT_BUDGET = 6
FATIGUE = {"on": {}, "off": {"fatigue_slope": 0.0}}


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def make_reviewer(args, pool, policy, registry):
    if args.reviewer == "heuristic":
        return HeuristicSafetyModel()
    from oversight.adapters.anthropic_client import AnthropicClient

    cache = ResponseCache(ROOT / "cache" / f"reviews_{args.model}.jsonl")
    actions = [registry.to_action(p.key, p.tool, p.params, p.description) for p in pool]
    client = AnthropicClient(model=args.model, effort=args.effort, json_schema=VERDICT_SCHEMA, client=None if not args.estimate else object())
    model = LLMSafetyModel(client, cache=cache, min_allow_confidence=0.0)
    todo = [a for a in actions if not model.is_cached(a)]
    est_in = sum((len(SYSTEM_PROMPT) + len(build_user_prompt(a))) // 3 + 50 for a in todo)
    print(f"[llm] {len(actions)} unique actions, {len(actions) - len(todo)} cached, {len(todo)} to review with {args.model}")
    print(f"[llm] estimated input ~{est_in:,} tok; cost ~${cost_usd(args.model, est_in, 600 * len(todo)):.2f} "
          f"(assumes ~600 output tok each), worst case ${cost_usd(args.model, est_in, client.max_tokens * len(todo)):.2f}")
    if args.estimate:
        sys.exit(0)
    model.spend = SpendTracker.from_env(default=1.0, ledger_path=ROOT / "cache" / "spend_ledger.jsonl")
    print(f"[llm] MAX_SPEND_USD=${model.spend.max_usd:.2f}, already spent ${model.spend.spent_usd:.4f}")
    for i, a in enumerate(todo, 1):
        try:
            model.review(a)
        except SpendLimitExceeded as e:
            sys.exit(f"[llm] stopped at {i - 1}/{len(todo)}: {e}. Cached reviews are kept; rerun with a higher cap to continue.")
        if i % 25 == 0:
            print(f"[llm] {i}/{len(todo)} reviewed, spent ${model.spend.spent_usd:.4f}")
    model.spend = None  # everything is cached now; the simulation spends nothing
    return model


def reviewer_accuracy(pool, registry, reviewer) -> dict:
    """Verdicts on every unique pool item, independent of routing."""
    table = defaultdict(lambda: defaultdict(int))
    for p in pool:
        v = reviewer.review(registry.to_action(p.key, p.tool, p.params, p.description)).verdict.value
        group = "benign" if not p.harmful else ("harmful_subtle" if p.subtle else "harmful_overt")
        table[group][v] += 1
        if not p.harmful and p.lookalike:
            table["benign_lookalike"][v] += 1
    return {g: dict(c) for g, c in table.items()}


def bootstrap_ci(num: list[float], den: list[float], rng: random.Random, n: int = 1000) -> tuple[float, float]:
    idx = range(len(num))
    stats = []
    for _ in range(n):
        s = [rng.choice(idx) for _ in idx]
        d = sum(den[i] for i in s)
        stats.append(sum(num[i] for i in s) / d if d else 0.0)
    stats.sort()
    return stats[int(0.025 * n)], stats[int(0.975 * n) - 1]


def aggregate(eps: list[dict], rng: random.Random) -> dict:
    tot = defaultdict(float)
    for m in eps:
        for k, v in m.items():
            tot[k] += v
    n = len(eps)
    lo, hi = bootstrap_ci([m["harmful_executed"] for m in eps], [m["harmful"] for m in eps], rng)
    return {
        "episodes": n,
        "actions": int(tot["actions"]),
        "harmful": int(tot["harmful"]),
        "harm_executed_pct": 100 * tot["harmful_executed"] / tot["harmful"],
        "harm_executed_ci95": [100 * lo, 100 * hi],
        "severity_executed_pct": 100 * tot["severity_executed"] / tot["severity_total"],
        "interrupts_per_day": tot["interrupts"] / n,
        "live_interrupts_per_day": tot["live_interrupts"] / n,
        "human_reviews_per_day": tot["human_reviews"] / n,
        "peak_interrupts_in_an_hour": tot["max_interrupts_in_hour"] / n,
        "benign_blocked_pct": 100 * tot["benign_blocked"] / tot["benign"],
        "benign_unresolved_pct": 100 * tot["benign_unresolved"] / tot["benign"],
        "deferred_per_day": tot["deferred"] / n,
        "mean_deferral_min": (tot["delay_seconds_sum"] / tot["delays_resolved"] / 60) if tot["delays_resolved"] else 0.0,
        "model_calls_per_day": tot["model_calls"] / n,
        "caught_by_model_pct": 100 * tot["caught_by_model"] / tot["harmful"],
        "caught_by_human_pct": 100 * tot["caught_by_human"] / tot["harmful"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reviewer", choices=["heuristic", "anthropic"], default="heuristic")
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="low")
    ap.add_argument("--estimate", action="store_true", help="print LLM cost estimate and exit")
    ap.add_argument("--quick", action="store_true", help="1 seed x 4 episodes smoke run")
    ap.add_argument("--out", default=None, help="results directory (default results/<reviewer>)")
    args = ap.parse_args()

    seeds, n_eps = ([0], 4) if args.quick else (SEEDS, EPISODES_PER_SEED)
    tag = args.reviewer if args.reviewer == "heuristic" else f"llm_{args.model}"
    out = Path(args.out) if args.out else ROOT / "results" / (tag + ("_quick" if args.quick else ""))
    out.mkdir(parents=True, exist_ok=True)

    policy = Policy.load(ROOT / "policies" / "default.yaml")
    registry = ToolRegistry.load(ROOT / "policies" / "tools.yaml", policy)
    pool = build_pool(0)
    reviewer = make_reviewer(args, pool, policy, registry)

    (ROOT / "data").mkdir(exist_ok=True)
    with (ROOT / "data" / "action_pool.jsonl").open("w") as f:
        for p in pool:
            f.write(json.dumps(p.to_dict(), sort_keys=True) + "\n")

    configs = [(s, None) for s in BASELINES] + [("adaptive", b) for b in BUDGETS_PER_HOUR]
    per_ep: dict[tuple, list[dict]] = defaultdict(list)
    t0 = time.time()
    for fatigue, hk in FATIGUE.items():
        for profile in PROFILES:
            for seed in seeds:
                for ep in range(n_eps):
                    ep_rng = random.Random(f"{seed}:{ep}")
                    events = sample_episode(pool, ep_rng)
                    schedule = make_schedule(profile, random.Random(f"{seed}:{ep}:{profile}"))
                    for strategy, budget in configs:
                        r = run_episode(events, schedule, strategy, policy, registry, reviewer, seed, ep, budget, hk)
                        per_ep[(fatigue, profile, strategy, budget)].append(r.metrics)
        print(f"fatigue={fatigue} done ({time.time() - t0:.0f}s)")

    rng = random.Random(0)
    rows = []
    for (fatigue, profile, strategy, budget), eps in sorted(per_ep.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], kv[0][3] or 0)):
        rows.append({"fatigue": fatigue, "profile": profile, "strategy": strategy, "budget_per_hour": budget, **aggregate(eps, rng)})
    for fatigue in FATIGUE:
        for strategy, budget in configs:
            eps = [m for p in PROFILES for m in per_ep[(fatigue, p, strategy, budget)]]
            rows.append({"fatigue": fatigue, "profile": "all", "strategy": strategy, "budget_per_hour": budget, **aggregate(eps, rng)})

    (out / "summary.json").write_text(json.dumps(rows, indent=1))
    with (out / "summary.csv").open("w", newline="") as f:
        flat = [{**r, "harm_executed_ci95": f"{r['harm_executed_ci95'][0]:.1f}-{r['harm_executed_ci95'][1]:.1f}"} for r in rows]
        w = csv.DictWriter(f, fieldnames=list(flat[0]))
        w.writeheader()
        w.writerows(flat)
    (out / "reviewer_accuracy.json").write_text(json.dumps(reviewer_accuracy(pool, registry, reviewer), indent=1, sort_keys=True))
    import yaml

    manifest = {
        "git_commit": git_commit(),
        "python": platform.python_version(),
        "reviewer": tag,
        "seeds": seeds,
        "episodes_per_seed": n_eps,
        "profiles": list(PROFILES),
        "budgets_per_hour": BUDGETS_PER_HOUR,
        "default_budget_per_hour": DEFAULT_BUDGET,
        "pool_size": len(pool),
        "pool_harmful": sum(p.harmful for p in pool),
        "policy": yaml.safe_load((ROOT / "policies" / "default.yaml").read_text()),
        "runtime_seconds": round(time.time() - t0, 1),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"wrote {out}/ ({len(rows)} rows) in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
