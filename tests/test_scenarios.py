import json
import random
import re
from collections import Counter
from pathlib import Path

from oversight.policy import Policy, Tier
from oversight.registry import ToolRegistry
from oversight.sim.availability import PROFILES, make_schedule
from oversight.sim.episodes import sample_episode
from oversight.sim.scenarios import BENIGN, HARMFUL, build_pool

ROOT = Path(__file__).parent.parent


def test_pool_deterministic_and_unique():
    a, b = build_pool(0), build_pool(0)
    assert [p.to_dict() for p in a] == [p.to_dict() for p in b]
    sigs = [repr((p.tool, sorted(p.params.items()), p.description)) for p in a]
    assert len(sigs) == len(set(sigs))
    assert len({p.key for p in a}) == len(a)


def test_pool_has_every_template_and_labels():
    pool = build_pool(0)
    assert {p.template for p in pool} == {t.id for t in BENIGN + HARMFUL}
    assert all(p.severity == 0 for p in pool if not p.harmful)
    assert all(1 <= p.severity <= 3 for p in pool if p.harmful)
    assert any(p.subtle for p in pool) and any(p.lookalike for p in pool)


def test_pool_is_synthetic_only():
    blob = json.dumps([p.to_dict() for p in build_pool(0)])
    for domain in re.findall(r"@([a-z][\w.-]+)", blob) + re.findall(r"https?://([\w.-]+)", blob):
        assert domain.endswith((".test", ".example")) or ".example." in domain or re.match(r"^\d", domain), domain
    for ip in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", blob):
        assert ip.startswith(("192.0.2.", "198.51.100.", "203.0.113.")), ip


def test_every_pool_item_maps_through_registry(policy_path):
    pol = Policy.load(policy_path)
    reg = ToolRegistry.load(ROOT / "policies" / "tools.yaml", pol)
    tiers = Counter(pol.assess(reg.to_action(p.key, p.tool, p.params, p.description)).tier for p in build_pool(0))
    assert set(tiers) == set(Tier)  # the pool exercises every tier


def test_episode_deterministic_sorted_and_rate():
    pool = build_pool(0)
    e1 = sample_episode(pool, random.Random(3))
    e2 = sample_episode(pool, random.Random(3))
    assert e1 == e2
    ts = [e.t for e in e1]
    assert ts == sorted(ts) and all(0 <= t < 8 * 3600 for t in ts)
    many = [e for s in range(30) for e in sample_episode(pool, random.Random(s))]
    rate = sum(e.item.harmful for e in many) / len(many)
    assert 0.05 < rate < 0.11
    assert 70 < len(many) / 30 < 125


def test_schedules():
    for prof in PROFILES:
        s1 = make_schedule(prof, random.Random(1))
        assert s1 == make_schedule(prof, random.Random(1))
        assert 0 <= s1.available_fraction() <= 1
        for (a, b), (c, d) in zip(s1.unavailable, s1.unavailable[1:]):
            assert a < b <= c < d
    away = make_schedule("away", random.Random(0))
    assert away.available(0) and not away.available(3600) and away.available(8 * 3600 - 60)
    assert away.available_fraction() < 0.2
