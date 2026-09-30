import random
from pathlib import Path

import pytest

from oversight.allocator import Allocator
from oversight.attention import AttentionTracker
from oversight.baselines import AlwaysHuman, AlwaysModel, NoOversight, StaticRisk
from oversight.gate import Outcome, OversightGate
from oversight.human import ConsoleHuman, SimulatedHuman, stable_uniform
from oversight.log import DecisionLog
from oversight.policies import DEFAULT_POLICY, DEFAULT_TOOLS
from oversight.policy import Policy
from oversight.registry import ToolRegistry
from oversight.safety_model import HeuristicSafetyModel
from oversight.schema import Route, SafetyVerdict, Verdict
from oversight.sim.availability import make_schedule
from oversight.sim.episodes import sample_episode
from oversight.sim.scenarios import build_pool
from oversight.sim.simulator import STRATEGIES, run_episode

ROOT = Path(__file__).parent.parent


class StubModel:
    name = "stub"

    def __init__(self, verdict, confidence=0.9):
        self.v = SafetyVerdict(Verdict(verdict), confidence, "stub", "stub")
        self.calls = 0

    def review(self, action):
        self.calls += 1
        return self.v


def allocator(policy_path, **kw):
    d = dict(window_seconds=3600, max_interrupts=6, min_gap_seconds=0)
    d.update(kw)
    return Allocator(Policy.load(policy_path), AttentionTracker(**d))


def medium(act):
    return act(category="exec")


def high(act):
    return act(category="financial", reversibility="costly", blast_radius="project")


# ---------------- gate ----------------
def test_low_executes_without_model(policy_path, act):
    m = StubModel("block")
    r = OversightGate(allocator(policy_path), m).review(act(), 0)
    assert r.outcome == Outcome.EXECUTE and m.calls == 0


@pytest.mark.parametrize("v,out", [("allow", Outcome.EXECUTE), ("block", Outcome.BLOCK), ("escalate", Outcome.ASK_HUMAN)])
def test_medium_follows_model(policy_path, act, v, out):
    assert OversightGate(allocator(policy_path), StubModel(v)).review(medium(act), 0).outcome == out


def test_low_confidence_allow_escalates(policy_path, act):
    r = OversightGate(allocator(policy_path), StubModel("allow", 0.5), min_allow_confidence=0.6).review(medium(act), 0)
    assert r.outcome == Outcome.ASK_HUMAN and r.decision.escalated


def test_degraded_uses_stricter_bar(policy_path, act):
    al = allocator(policy_path)
    al.attention.set_available(False)
    g = OversightGate(al, StubModel("allow", 0.8), 0.6, 0.85)
    r = g.review(high(act), 0)
    assert r.decision.degraded and r.outcome == Outcome.DEFER  # 0.8 < 0.85 and no human reachable
    g2 = OversightGate(al, StubModel("allow", 0.9), 0.6, 0.85)
    assert g2.review(high(act), 1).outcome == Outcome.EXECUTE


def test_escalation_respects_budget(policy_path, act):
    al = allocator(policy_path, max_interrupts=1)
    g = OversightGate(al, StubModel("escalate"))
    assert g.review(medium(act), 0).outcome == Outcome.ASK_HUMAN
    assert g.review(medium(act), 1).outcome == Outcome.DEFER


def test_critical_never_reaches_model(policy_path, act):
    m = StubModel("allow")
    r = OversightGate(allocator(policy_path), m).review(act(category="admin", reversibility="irreversible"), 0)
    assert r.outcome == Outcome.ASK_HUMAN and m.calls == 0


def test_from_policy_reads_thresholds(policy_path):
    g = OversightGate.from_policy(Policy.load(policy_path), allocator(policy_path), None)
    assert (g.min_allow_confidence, g.degraded_min_allow_confidence) == (0.6, 0.85)


def test_gate_logs_every_step(tmp_path, policy_path, act):
    log = DecisionLog(tmp_path / "g.jsonl")
    g = OversightGate(allocator(policy_path), StubModel("escalate"), log=log)
    a = medium(act)
    g.review(a, 0)
    g.record_human(a, True, 5, "ok")
    recs = log.records()
    assert [r["event"] for r in recs] == ["gate", "human"]
    assert recs[0]["verdict"]["verdict"] == "escalate" and recs[0]["reasons"]


# ---------------- baselines ----------------
def test_baseline_routes(policy_path, act):
    pol = Policy.load(policy_path)
    att = lambda: AttentionTracker(3600, 10**9, 0)  # noqa: E731
    assert NoOversight(pol, att()).decide(act(category="admin", reversibility="irreversible"), 0).route == Route.SELF
    assert AlwaysModel(pol, att()).decide(act(), 0).route == Route.SAFETY_MODEL
    assert AlwaysHuman(pol, att()).decide(act(), 0).route == Route.HUMAN
    s = StaticRisk(pol, att())
    assert [s.decide(x, 0).route for x in (act(), medium(act), high(act))] == [Route.SELF, Route.SAFETY_MODEL, Route.HUMAN]


def test_baseline_defers_when_unavailable(policy_path, act):
    a = AttentionTracker(3600, 10**9, 0)
    a.set_available(False)
    assert AlwaysHuman(Policy.load(policy_path), a).decide(act(), 0).deferred


# ---------------- humans ----------------
def test_stable_uniform():
    assert stable_uniform(1, "a") == stable_uniform(1, "a") != stable_uniform(2, "a")
    assert 0 <= stable_uniform("x") < 1


def test_simulated_human_fatigue_lowers_detection():
    h = SimulatedHuman({}, fatigue_threshold=2, fatigue_slope=0.1, p_detect=0.9, floor=0.5)
    assert h.detect_probability(0) == 0.9
    h.review_times.extend([0, 1, 2, 3, 4])
    assert h.detect_probability(10) == pytest.approx(0.6)
    assert h.detect_probability(4000) == 0.9  # recovered after an hour


def test_simulated_human_perfect_and_blind(act):
    a = act(id="x")
    assert not SimulatedHuman({"x": True}, p_detect=1.0).review(a, 0).approved
    assert SimulatedHuman({"x": True}, p_detect=0.0, floor=0.0).review(a, 0).approved
    assert SimulatedHuman({"x": False}, p_false_block=0.0).review(a, 0).approved


def test_console_human(act):
    assert ConsoleHuman(ask=lambda p: "y").review(act(), 0).approved
    assert not ConsoleHuman(ask=lambda p: "").review(act(), 0).approved


# ---------------- simulator ----------------
@pytest.fixture(scope="module")
def world():
    pol = Policy.load(DEFAULT_POLICY)
    reg = ToolRegistry.load(DEFAULT_TOOLS, pol)
    pool = build_pool(0)
    events = sample_episode(pool, random.Random(11))
    return pol, reg, events


def run(world, strategy, profile="focused", **kw):
    pol, reg, events = world
    return run_episode(events, make_schedule(profile, random.Random(5)), strategy, pol, reg, HeuristicSafetyModel(), seed=0, episode=0, **kw)


def test_every_action_resolved_and_counted(world):
    for s in STRATEGIES:
        r = run(world, s)
        m = r.metrics
        assert m["actions"] == len(world[2]) == m["harmful"] + m["benign"]
        assert all(row["executed"] in (True, False) for row in r.rows)
        assert m["route_self"] + m["route_model"] + m["route_human"] == m["actions"]


def test_no_oversight_executes_everything(world):
    m = run(world, "no_oversight").metrics
    assert m["harmful_executed"] == m["harmful"] and m["interrupts"] == 0 and m["model_calls"] == 0


def test_always_human_never_calls_model(world):
    m = run(world, "always_human").metrics
    assert m["model_calls"] == 0 and m["human_reviews"] == m["actions"]


def test_simulation_is_deterministic(world):
    assert run(world, "adaptive").metrics == run(world, "adaptive").metrics


def test_tighter_budget_never_increases_interrupts(world):
    live = [run(world, "adaptive", budget_per_hour=b).metrics["live_interrupts"] for b in (1, 2, 4, 8)]
    # critical actions bypass the budget, so this is monotone but not proportional
    assert live == sorted(live)


def test_away_profile_defers_and_queues(world):
    m = run(world, "static_risk", profile="away").metrics
    assert m["deferred"] > 0 and m["batch_sessions"] >= 1


def test_simulation_writes_audit_log(world, tmp_path):
    log = DecisionLog(tmp_path / "sim.jsonl")
    r = run(world, "adaptive", log=log)
    gates = [x for x in log.records() if x["event"] == "gate"]
    assert len(gates) == r.metrics["actions"]
