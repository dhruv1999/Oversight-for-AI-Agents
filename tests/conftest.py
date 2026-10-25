from agent_ratchet import CaseResult, CheckResult, RunResult, SuiteResult, ToolCall, Trajectory


def traj(*tools, output="done", **kw):
    calls = [t if isinstance(t, ToolCall) else ToolCall(t) for t in tools]
    return Trajectory(input="hi", output=output, tool_calls=calls, **kw)


def case_result(name, passes, n, cost=None, latency=None, must_pass=False, fingerprint=None):
    """A case result with `passes` passing runs out of `n`; failures fail one check."""
    runs = [RunResult(i + 1, Trajectory(cost_usd=cost, latency_s=latency), [] if i < passes else [_fail()]) for i in range(n)]
    return CaseResult(name, runs, must_pass, fingerprint)


def suite_result(*cases, created=None):
    r = SuiteResult("s", list(cases))
    if created:
        r.created = created
    return r


def _fail():
    return CheckResult("answer contains 'x'", False, "missing ['x']")
