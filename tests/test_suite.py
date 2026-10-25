import asyncio
import json
import threading
import time

import pytest

import agent_ratchet.suite as suite_module
from agent_ratchet import Case, Suite, SuiteResult, Trajectory, expect, record_usage, tool


@tool
def lookup(order_id: str) -> str:
    return "shipped"


def agent(message: str) -> str:
    record_usage(1000, 100)
    if "order" in message:
        lookup("42")
    return "ok"


def test_runs_each_case_several_times():
    s = Suite(agent, [Case("a", "order 42", [expect.calls("lookup")]), Case("b", "hello", [expect.calls("lookup")], repeats=2)], repeats=3)
    r = s.run()
    assert s.name == "agent"
    assert [(c.name, c.passes, c.n) for c in r.cases] == [("a", 3, 3), ("b", 0, 2)]
    assert not r.ok
    assert r.case("b").failing_checks == {"calls lookup()": 2}
    assert "never called lookup" in r.case("b").example_failure("calls lookup()")


def test_price_fills_cost_and_latency_is_measured():
    r = Suite(agent, [Case("a", "x")], repeats=1, price_per_mtok=(3.0, 15.0)).run()
    t = r.cases[0].runs[0].trajectory
    assert t.cost_usd == pytest.approx((1000 * 3 + 100 * 15) / 1e6)
    assert r.cost_usd == pytest.approx(t.cost_usd)
    assert t.latency_s is not None


def test_crash_is_a_failed_run_not_a_crashed_suite():
    def bad(_):
        lookup("1")
        raise RuntimeError("boom")

    c = Suite(bad, [Case("a", "x")], repeats=2).run().cases[0]
    assert c.passes == 0 and c.failing_checks["run crashed"] == 2
    assert c.runs[0].trajectory.tools == ["lookup"]
    assert "RuntimeError: boom" in c.example_failure("run crashed")


def test_async_agents_and_returned_trajectories():
    async def a_agent(message):
        await asyncio.sleep(0)
        lookup("1")
        return "fine"

    def traj_agent(message):
        return Trajectory(output="t", input=None)

    def returns_coroutine(message):  # a plain function that hands back a coroutine: its tool calls still count
        return a_agent(message)

    assert Suite(a_agent, [Case("a", "x", [expect.calls("lookup"), expect.output_contains("fine")])]).run().ok
    r = Suite(traj_agent, [Case("a", "x", [expect.output_contains("t")])], repeats=1).run()
    assert r.ok and r.cases[0].runs[0].trajectory.input == "x"
    assert Suite(returns_coroutine, [Case("a", "x", [expect.calls("lookup")])], repeats=1).run().ok


def test_concurrency_limit_is_respected():
    lock, state = threading.Lock(), {"now": 0, "peak": 0}

    def slow(_):
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        time.sleep(0.05)
        with lock:
            state["now"] -= 1
        return "ok"

    Suite(slow, [Case(str(i), "x") for i in range(6)], repeats=2, concurrency=3).run()
    assert state["peak"] == 3


def test_a_hung_run_times_out_and_the_suite_finishes():
    def hangs(_):
        time.sleep(5)

    async def hangs_async(_):
        await asyncio.sleep(5)

    start = time.perf_counter()
    for fn in (hangs, hangs_async):
        c = Suite(fn, [Case("a", "x")], repeats=2, timeout=0.2).run().cases[0]
        assert c.passes == 0 and c.example_failure("run crashed") == "timed out after 0.2s"
    assert time.perf_counter() - start < 3


class Overloaded(Exception):
    status_code = 529


def test_provider_errors_are_retried_but_agent_errors_are_not(monkeypatch):
    monkeypatch.setattr(suite_module, "RETRY_DELAY_S", 0)
    calls = {"flaky": 0, "wrapped": 0, "broken": 0}

    def flaky(_):
        calls["flaky"] += 1
        if calls["flaky"] == 1:
            raise Overloaded("try again")
        return "ok"

    def wrapped(_):
        calls["wrapped"] += 1
        if calls["wrapped"] == 1:
            try:
                raise Overloaded("try again")
            except Overloaded as e:
                raise RuntimeError("framework error") from e
        return "ok"

    def broken(_):
        calls["broken"] += 1
        raise KeyError("missing")

    assert Suite(flaky, [Case("a", "x")], repeats=1).run().ok and calls["flaky"] == 2
    assert Suite(wrapped, [Case("a", "x")], repeats=1).run().ok and calls["wrapped"] == 2
    assert not Suite(broken, [Case("a", "x")], repeats=1).run().ok and calls["broken"] == 1


def test_cases_that_look_worse_get_more_runs():
    cases = [Case("refund", "order 1", [expect.calls("lookup")]), Case("hello", "hi")]
    baseline = Suite(agent, cases, max_repeats=8).run(repeats=8)

    def forgets_lookup(message):
        return "ok"

    same = Suite(agent, cases, max_repeats=8).run(baseline=baseline)
    worse = Suite(forgets_lookup, cases, max_repeats=8).run(baseline=baseline)
    assert [c.n for c in same.cases] == [3, 3]  # nothing looks worse: no extra cost
    assert [c.n for c in worse.cases] == [8, 3]  # only the case that dropped is rerun
    assert [r.attempt for r in worse.case("refund").runs] == list(range(1, 9))

    edited = [Case("refund", "order 1", [expect.calls("lookup"), expect.max_tool_calls(1)])]
    assert Suite(forgets_lookup, edited, max_repeats=8).run(baseline=baseline).cases[0].n == 3  # changed case: not compared
    critical = [Case("refund", "order 1", [expect.calls("lookup")], must_pass=True)]
    assert Suite(forgets_lookup, critical, max_repeats=8).run(baseline=baseline).cases[0].n == 3  # must pass: one failure is enough


def test_must_pass_and_fingerprints():
    r = Suite(agent, [Case("a", "hi", [expect.calls("lookup")], must_pass=True), Case("b", "hi")], repeats=2).run()
    assert [c.name for c in r.must_pass_failures] == ["a"]
    a = Case("a", {"text": "x", "n": 1}, [expect.calls("lookup")])
    assert a.fingerprint == Case("other name", {"n": 1, "text": "x"}, [expect.calls("lookup")]).fingerprint
    assert a.fingerprint != Case("a", {"text": "y", "n": 1}, [expect.calls("lookup")]).fingerprint
    assert a.fingerprint != Case("a", {"text": "x", "n": 1}, [expect.calls("lookup", order_id="1")]).fingerprint


def test_saved_baselines_hold_no_run_content(tmp_path):
    def leaky(message):
        lookup("customer-secret-42")
        raise ValueError("token sk-123 rejected")

    r = Suite(leaky, [Case("a", "my card is 4111", [expect.calls("lookup")])], repeats=2, price_per_mtok=(1, 1)).run()
    full = json.loads(r.save(tmp_path / "latest.json").read_text(encoding="utf-8"))
    slim_text = r.save(tmp_path / "baseline.json", full=False).read_text(encoding="utf-8")
    assert "customer-secret-42" in json.dumps(full)
    for secret in ("4111", "customer-secret-42", "sk-123"):
        assert secret not in slim_text
    back = SuiteResult.load(tmp_path / "baseline.json")
    assert back.case("a").n == 2 and back.case("a").failing_checks == {"run crashed": 2}
    assert back.case("a").fingerprint == r.case("a").fingerprint


def test_save_load_merge_and_subset(tmp_path):
    full = Suite(agent, [Case("a", "order 42", [expect.calls("lookup")]), Case("b", "hi")], repeats=2).run()
    back = SuiteResult.load(full.save(tmp_path / "r.json"))
    assert back.case("a").runs[0].trajectory.tool_calls[0].args == {"order_id": "42"}
    partial = Suite(agent, [Case("b", "hi"), Case("c", "hi")], repeats=1).run()
    merged = back.merged(partial)
    assert [(c.name, c.n) for c in merged.cases] == [("a", 2), ("b", 1), ("c", 1)]
    assert [c.name for c in merged.subset(["c", "a"]).cases] == ["a", "c"]
    newer = full.to_dict()
    newer["format"] = 99
    with pytest.raises(ValueError, match="newer version"):
        SuiteResult.from_dict(newer)


def test_validation():
    with pytest.raises(ValueError):
        Suite(agent, [Case("a", 1), Case("a", 2)])
    with pytest.raises(ValueError):
        Suite(agent, [Case("a", 1)], repeats=5, max_repeats=3)
    with pytest.raises(ValueError):
        Suite(agent, [Case("a", 1)], timeout=0)
    s = Suite(agent, [Case("a", "x"), Case("b", "y")], repeats=1)
    assert [c.name for c in s.run(only=["b"]).cases] == ["b"]
    with pytest.raises(ValueError):
        s.run(only=["zzz"])

    async def inside_a_loop():
        with pytest.raises(RuntimeError, match="arun"):
            s.run()
        return (await s.arun()).ok

    assert asyncio.run(inside_a_loop())
