import pytest
from conftest import case_result, suite_result

from agent_ratchet import compare
from agent_ratchet.compare import CHANGED, IMPROVED, NEW, REGRESSED, REMOVED, SAME
from agent_ratchet.report import markdown, text


def test_statuses():
    before = suite_result(
        case_result("broken", 10, 10),
        case_result("fixed", 0, 10),
        case_result("noise", 10, 10),
        case_result("edited", 10, 10, fingerprint="aaa"),
        case_result("gone", 5, 5),
    )
    after = suite_result(
        case_result("broken", 0, 10),
        case_result("fixed", 10, 10),
        case_result("noise", 9, 10),
        case_result("edited", 0, 10, fingerprint="bbb"),
        case_result("new", 5, 5),
    )
    c = compare(after, before)
    status = {d.name: d.status for d in c.diffs}
    assert status == {"broken": REGRESSED, "fixed": IMPROVED, "noise": SAME, "edited": CHANGED, "new": NEW, "gone": REMOVED}
    assert not c.ok and [d.name for d in c.regressions] == ["broken"]
    assert c.regressions[0].chance == pytest.approx(1 / 184756)
    assert "answer contains 'x': failed 10/10, baseline 0/10" in c.regressions[0].notes[0]
    noise = next(d for d in c.diffs if d.name == "noise")
    assert noise.looks_worse and noise.chance == pytest.approx(0.5)


def test_one_failure_in_three_runs_is_not_a_regression():
    # the rule this replaces failed the build here, so any suite with flaky cases failed most pull requests
    c = compare(suite_result(case_result("a", 2, 3)), suite_result(case_result("a", 10, 10)))
    assert c.ok and c.diffs[0].looks_worse


def test_many_borderline_drops_do_not_add_up_to_false_alarms():
    one = compare(suite_result(case_result("a", 3, 10)), suite_result(case_result("a", 8, 10)))
    assert not one.ok  # alone, 80% -> 30% is significant (3.5%)
    names = [str(i) for i in range(10)]
    many = compare(suite_result(*(case_result(n, 3, 10) for n in names)), suite_result(*(case_result(n, 8, 10) for n in names)))
    assert many.ok  # ten such drops at once: each could be chance, so the threshold tightens
    stable = [case_result(f"s{i}", 10, 10) for i in range(50)]
    diluted = compare(suite_result(case_result("a", 3, 10), *stable), suite_result(case_result("a", 8, 10), *stable))
    assert not diluted.ok  # fifty stable cases cannot regress, so they do not count against it


def test_confidence():
    before, after = suite_result(case_result("a", 3, 3)), suite_result(case_result("a", 0, 3))
    assert not compare(after, before).ok  # chance is exactly 5%
    assert compare(after, before, confidence=0.99).ok
    with pytest.raises(ValueError):
        compare(after, before, confidence=95)


def test_cost_and_latency_budgets():
    before = suite_result(case_result("a", 3, 3, cost=0.010, latency=1.0))
    after = suite_result(case_result("a", 3, 3, cost=0.015, latency=1.1))
    assert compare(after, before).ok  # reported, not enforced
    c = compare(after, before, max_cost_increase=0.25)
    assert not c.ok and c.over_budget[0].cost_change == pytest.approx(0.5)
    assert compare(after, before, max_latency_increase=0.05).over_budget


def test_text_report_explains_each_verdict():
    before = suite_result(
        case_result("refund", 10, 10, cost=0.01), case_result("status", 10, 10), case_result("tone", 10, 10), created="2020-01-01T00:00:00+00:00"
    )
    after = suite_result(
        case_result("refund", 0, 10, cost=0.01), case_result("status", 10, 10), case_result("tone", 2, 3), case_result("guard", 2, 3, must_pass=True)
    )
    c = compare(after, before)
    t = text(after, c)
    assert "REGRESSED" in t and "refund: passed 0/10, baseline 10/10. A drop this large happens by chance under 0.1% of the time." in t
    assert "tone: passed 2/3, baseline 10/10. That could be chance" in t
    assert "FAILED (must pass)" in t and "guard: must pass, but failed 1 of 3 runs" in t
    assert "The baseline is" in t and "days old" in t
    assert "1 regressed" in t and "1 must pass cases failed" in t and "cost $0.1000" in t
    assert "status:" not in t  # a case as good as its baseline stays quiet
    plain = text(suite_result(case_result("refund", 0, 3), case_result("status", 2, 3)))
    assert "failing" in plain and "flaky" in plain and "regressed" not in plain


def test_markdown_report():
    before = suite_result(case_result("refund | large", 10, 10, cost=0.01), case_result("edited", 3, 3, fingerprint="a"))
    after = suite_result(case_result("refund | large", 0, 10, cost=0.01), case_result("edited", 3, 3, fingerprint="b"))
    md = markdown(after, compare(after, before))
    assert md.startswith("### agent-ratchet: s") and "**1 regressed**" in md
    assert "| refund \\| large | 0/10 | 10/10 | 🔻 regressed | $0.0100 (+0%) |" in md
    assert "✅ ok (changed)" in md and "Save a new baseline" in md
