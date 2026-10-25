from conftest import case_result, suite_result

from agent_regress import compare
from agent_regress.compare import IMPROVED, NEW, REGRESSED, REMOVED, SAME
from agent_regress.report import markdown, text


def test_statuses():
    before = suite_result(case_result("a", 5, 5), case_result("b", 1, 5), case_result("c", 5, 5), case_result("gone", 5, 5))
    after = suite_result(case_result("a", 1, 5), case_result("b", 5, 5), case_result("c", 4, 5), case_result("new", 5, 5))
    c = compare(after, before)
    status = {d.name: d.status for d in c.diffs}
    assert status == {"a": REGRESSED, "b": IMPROVED, "c": SAME, "new": NEW, "gone": REMOVED}
    assert not c.ok and [d.name for d in c.regressions] == ["a"]
    assert "answer contains 'x': failed 4/5" in c.regressions[0].notes[0]


def test_confidence_needs_enough_runs():
    big = compare(suite_result(case_result("a", 0, 20)), suite_result(case_result("a", 20, 20)))
    assert big.regressions[0].confident
    noisy = compare(suite_result(case_result("a", 3, 5)), suite_result(case_result("a", 5, 5)))
    assert noisy.regressions[0].confident is False


def test_tolerance():
    before, after = suite_result(case_result("a", 5, 5)), suite_result(case_result("a", 4, 5))
    assert compare(after, before).ok
    assert not compare(after, before, tolerance=0.2).ok


def test_cost_and_latency_budgets():
    before = suite_result(case_result("a", 3, 3, cost=0.010, latency=1.0))
    after = suite_result(case_result("a", 3, 3, cost=0.015, latency=1.1))
    assert compare(after, before).ok  # reported, not enforced
    c = compare(after, before, max_cost_increase=0.25)
    assert not c.ok and c.over_budget[0].cost_change == 0.5
    assert compare(after, before, max_latency_increase=0.05).over_budget


def test_reports():
    before = suite_result(case_result("refund", 3, 3, cost=0.01), case_result("status", 3, 3))
    after = suite_result(case_result("refund", 0, 3, cost=0.01), case_result("status", 3, 3))
    c = compare(after, before)
    t = text(after, c)
    assert "REGRESSED" in t and "pass rate 100% -> 0%" in t and "1 regressed" in t
    md = markdown(after, c)
    assert md.startswith("### agent-regress: s") and "| refund | 0/3 | 3/3 |" in md and "**1 regressed**" in md
    plain = text(suite_result(case_result("refund", 0, 3), case_result("status", 2, 3)))
    assert "failing" in plain and "flaky" in plain and "regressed" not in plain
