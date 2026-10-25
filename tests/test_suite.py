import asyncio
import time

import pytest

from agent_regress import Case, Suite, SuiteResult, Trajectory, expect, record_usage, tool
from agent_regress.stats import wilson


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

    r = Suite(a_agent, [Case("a", "x", [expect.calls("lookup"), expect.output_contains("fine")])]).run()
    assert r.ok
    r = Suite(traj_agent, [Case("a", "x", [expect.output_contains("t")])], repeats=1).run()
    assert r.ok and r.cases[0].runs[0].trajectory.input == "x"


def test_concurrency_runs_in_parallel():
    def slow(_):
        time.sleep(0.2)
        return "ok"

    start = time.perf_counter()
    Suite(slow, [Case(str(i), "x") for i in range(4)], repeats=2, concurrency=8).run()
    assert time.perf_counter() - start < 1.0


def test_validation_and_case_filter():
    with pytest.raises(ValueError):
        Suite(agent, [Case("a", 1), Case("a", 2)])
    s = Suite(agent, [Case("a", "x"), Case("b", "y")], repeats=1)
    assert [c.name for c in s.run(only=["b"]).cases] == ["b"]
    with pytest.raises(ValueError):
        s.run(only=["zzz"])


def test_save_and_load_round_trip(tmp_path):
    r = Suite(agent, [Case("a", "order 42", [expect.calls("lookup")])], repeats=2).run()
    back = SuiteResult.load(r.save(tmp_path / "r.json"))
    assert back.case("a").passes == 2
    assert back.case("a").runs[0].trajectory.tool_calls[0].args == {"order_id": "42"}


def test_wilson():
    assert wilson(0, 0) == (0.0, 1.0)
    lo, hi = wilson(3, 3)
    assert 0.4 < lo < 0.5 and hi == pytest.approx(1.0)
