import json

from oversight.allocator import Allocator
from oversight.attention import AttentionTracker
from oversight.log import DecisionLog
from oversight.metrics import summarize
from oversight.policy import Policy


def run(policy_path, act):
    al = Allocator(Policy.load(policy_path), AttentionTracker(3600, 1, 0))
    acts = [
        act(id="1"),
        act(id="2", category="exec"),
        act(id="3", category="financial", reversibility="costly", blast_radius="project"),
        act(id="4", category="financial", reversibility="costly", blast_radius="project"),  # degraded
    ]
    return [al.decide(a, now=i) for i, a in enumerate(acts)]


def test_summary_counts(policy_path, act):
    s = summarize(run(policy_path, act))
    assert s["total"] == 4
    assert s["routes"] == {"self": 1, "safety_model": 2, "human": 1}
    assert s["degraded"] == 1 and s["deferred"] == 0
    assert s["human_interrupts"] == 1


def test_fractions_sum_to_one(policy_path, act):
    s = summarize(run(policy_path, act))
    assert abs(sum(s["route_fractions"].values()) - 1) < 1e-9


def test_empty_summary():
    s = summarize([])
    assert s["total"] == 0 and s["human_interrupts"] == 0


def test_log_roundtrip(tmp_path, policy_path, act):
    ds = run(policy_path, act)
    log = DecisionLog(tmp_path / "d.jsonl")
    for d in ds:
        log.append(d)
    rows = [json.loads(line) for line in (tmp_path / "d.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 4 and rows[0]["route"] == "self" and rows[0]["reasons"]
    assert [d.to_dict() for d in log.read()] == [d.to_dict() for d in ds]
