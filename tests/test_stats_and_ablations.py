import json
import random
import subprocess
import sys
from pathlib import Path

import pytest

from oversight.allocator import Allocator
from oversight.attention import AttentionTracker
from oversight.policies import DEFAULT_POLICY
from oversight.policy import Policy
from oversight.schema import Route
from oversight.sim.stats import paired_difference, ratio_ci, wilson

ROOT = Path(__file__).parent.parent


def test_wilson_known_values():
    lo, hi = wilson(0, 10)
    assert lo == 0 and 0.27 < hi < 0.29  # textbook: [0, 0.278]
    lo, hi = wilson(50, 100)
    assert 0.40 < lo < 0.41 and 0.59 < hi < 0.60
    assert wilson(0, 0) == (0.0, 1.0)


def test_ratio_ci_brackets_point():
    num, den = [1, 2, 3, 4] * 10, [10] * 40
    lo, hi = ratio_ci(num, den, random.Random(0))
    assert lo <= 0.25 <= hi


def ep(harm_exec, harm, interrupts):
    return {"harmful_executed": harm_exec, "harmful": harm, "interrupts": interrupts}


def test_paired_difference_identical_is_zero():
    a = [ep(1, 10, 5)] * 30
    d = paired_difference(a, list(a), random.Random(0), n=200)
    assert d["harm_diff_points"] == 0 and d["harm_diff_ci95"] == [0, 0] and d["interrupts_diff_per_day"] == 0


def test_paired_difference_detects_consistent_gain():
    a = [ep(1, 10, 3 + i % 2) for i in range(50)]
    b = [ep(2, 10, 6 + i % 2) for i in range(50)]
    d = paired_difference(a, b, random.Random(0), n=500)
    assert d["harm_diff_points"] == pytest.approx(-10) and d["harm_diff_ci95"][1] < 0
    assert d["interrupts_diff_per_day"] == pytest.approx(-3) and d["interrupts_diff_ci95"][1] < 0


def test_paired_difference_rejects_mismatch():
    with pytest.raises(ValueError):
        paired_difference([ep(0, 1, 0)], [], random.Random(0))


def test_allocator_without_checker_fallback_waits(act):
    pol = Policy.load(DEFAULT_POLICY)
    al = Allocator(pol, AttentionTracker(3600, 0, 0), fallback_to_checker=False)
    d = al.decide(act(category="financial", reversibility="costly", blast_radius="project"), 0)
    assert d.route == Route.HUMAN and d.deferred and not d.degraded


def test_robustness_quick_run(tmp_path):
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_robustness.py"), "--quick"], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    assert r.returncode == 0, r.stderr
    data = json.loads((ROOT / "results" / "heuristic_quick" / "robustness.json").read_text(encoding="utf-8"))
    names = [v["name"] for v in data["variants"]]
    assert names[0] == "Baseline assumptions" and len(names) == 14
    assert {a["strategy"] for a in data["budget_drain_attack"]} == {"adaptive", "static_risk"}


def test_counting_each_queued_review_raises_interrupts():
    from oversight.policies import DEFAULT_TOOLS
    from oversight.registry import ToolRegistry
    from oversight.safety_model import HeuristicSafetyModel
    from oversight.sim.availability import make_schedule
    from oversight.sim.episodes import sample_episode
    from oversight.sim.scenarios import build_pool
    from oversight.sim.simulator import run_episode

    pol = Policy.load(DEFAULT_POLICY)
    reg = ToolRegistry.load(DEFAULT_TOOLS, pol)
    events = sample_episode(build_pool(0), random.Random(1))
    sched = make_schedule("away", random.Random(1))
    once = run_episode(events, sched, "static_risk", pol, reg, HeuristicSafetyModel(), 0, 0).metrics
    each = run_episode(events, sched, "static_risk", pol, reg, HeuristicSafetyModel(), 0, 0, batch_counts_once=False).metrics
    assert each["interrupts"] > once["interrupts"] and each["harmful_executed"] >= 0
