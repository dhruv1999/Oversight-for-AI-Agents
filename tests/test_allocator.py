from oversight.allocator import Allocator
from oversight.attention import AttentionTracker
from oversight.policy import Policy, Tier
from oversight.schema import Route


def make(policy_path, **kw):
    d = dict(window_seconds=3600, max_interrupts=6, min_gap_seconds=0)
    d.update(kw)
    return Allocator(Policy.load(policy_path), AttentionTracker(**d))


def high(act, **kw):
    return act(category="financial", reversibility="costly", blast_radius="project", **kw)  # score 8


def crit(act):
    return act(category="admin", reversibility="irreversible")


def test_low_goes_self(policy_path, act):
    d = make(policy_path).decide(act(), now=0)
    assert d.route == Route.SELF and d.tier == "low"


def test_medium_goes_safety_model(policy_path, act):
    d = make(policy_path).decide(act(category="exec"), now=0)
    assert d.route == Route.SAFETY_MODEL


def test_high_goes_human_when_attentive(policy_path, act):
    d = make(policy_path).decide(high(act), now=0)
    assert d.route == Route.HUMAN and not d.deferred and not d.degraded


def test_high_degrades_to_safety_model_when_human_unavailable(policy_path, act):
    al = make(policy_path)
    al.attention.set_available(False)
    d = al.decide(high(act), now=0)
    assert d.route == Route.SAFETY_MODEL and d.degraded
    assert any("unavailable" in r for r in d.reasons)


def test_high_degrades_when_budget_exhausted(policy_path, act):
    al = make(policy_path, max_interrupts=1)
    assert al.decide(high(act, ), now=0).route == Route.HUMAN
    d = al.decide(high(act), now=1)
    assert d.route == Route.SAFETY_MODEL and d.degraded


def test_critical_always_human_even_over_budget(policy_path, act):
    al = make(policy_path, max_interrupts=0)
    d = al.decide(crit(act), now=0)
    assert d.route == Route.HUMAN and not d.deferred


def test_critical_deferred_when_human_unavailable(policy_path, act):
    al = make(policy_path)
    al.attention.set_available(False)
    d = al.decide(crit(act), now=0)
    assert d.route == Route.HUMAN and d.deferred  # never falls back to a model


def test_human_route_consumes_budget(policy_path, act):
    al = make(policy_path)
    al.decide(high(act), now=0)
    assert al.attention.interrupts_in_window(0) == 1


def test_non_human_routes_do_not_consume_budget(policy_path, act):
    al = make(policy_path)
    al.decide(act(), now=0)
    al.decide(act(category="exec"), now=1)
    assert al.attention.interrupts_in_window(1) == 0


def test_every_decision_has_reasons_and_ids(policy_path, act):
    d = make(policy_path).decide(act(id="zzz"), now=5)
    assert d.action_id == "zzz" and d.reasons and d.timestamp == 5


def test_deterministic(policy_path, act):
    a = make(policy_path)
    b = make(policy_path)
    seq = [act(), act(category="exec"), high(act), crit(act)]
    assert [a.decide(x, now=i).route for i, x in enumerate(seq)] == [
        b.decide(x, now=i).route for i, x in enumerate(seq)
    ]


def test_critical_decision_is_budget_exempt_high_is_not(policy_path, act):
    al = make(policy_path)
    assert al.decide(crit(act), now=0).budget_exempt
    assert not al.decide(high(act), now=1).budget_exempt
