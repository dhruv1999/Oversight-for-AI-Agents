from agent_regress import CaseResult, RunResult, SuiteResult, ToolCall, Trajectory


def traj(*tools, output="done", **kw):
    calls = [t if isinstance(t, ToolCall) else ToolCall(t) for t in tools]
    return Trajectory(input="hi", output=output, tool_calls=calls, **kw)


def case_result(name, passes, n, cost=None, latency=None):
    runs = [RunResult(i + 1, Trajectory(cost_usd=cost, latency_s=latency), [] if i < passes else [_fail()]) for i in range(n)]
    return CaseResult(name, runs)


def suite_result(*cases):
    return SuiteResult("s", list(cases))


def _fail():
    from agent_regress import CheckResult

    return CheckResult("answer contains 'x'", False, "missing ['x']")
