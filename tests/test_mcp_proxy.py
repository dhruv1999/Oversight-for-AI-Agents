"""The MCP proxy end to end: a real MCP client talks to `oversight mcp -- <toy server>`."""

import sys
from pathlib import Path

import pytest

mcp = pytest.importorskip("mcp")
anyio = pytest.importorskip("anyio")

from mcp import ClientSession, types  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

TOY = Path(__file__).parent / "fixtures" / "toy_mcp_server.py"


def text(result) -> str:
    return "".join(c.text for c in result.content if getattr(c, "type", "") == "text")


async def session_run(steps, answer=None, state_dir=None):
    """Start the proxy in front of the toy server and run `steps(session)`. `answer` is the person's reply."""
    asked = []

    async def on_elicit(context, params):
        asked.append(params.message)
        return types.ElicitResult(action="accept", content={"approve": answer})

    args = ["-m", "oversight.cli"] + (["--state", str(state_dir)] if state_dir else []) + ["mcp", "--", sys.executable, str(TOY)]
    params = StdioServerParameters(command=sys.executable, args=args)
    async with stdio_client(params) as (r, w):
        kwargs = {"elicitation_callback": on_elicit} if answer is not None else {}
        async with ClientSession(r, w, **kwargs) as session:
            await session.initialize()
            return await steps(session), asked


def run(steps, answer=None, state_dir=None):
    return anyio.run(session_run, steps, answer, state_dir)


def test_same_tools_and_low_risk_runs():
    async def steps(s):
        tools = await s.list_tools()
        res = await s.call_tool("read_file", {"path": "notes.txt"})
        return [t.name for t in tools.tools], res

    (names, res), asked = run(steps)
    assert sorted(names) == ["pay_invoice", "read_file", "run_sql"]
    assert not res.is_error and text(res) == "contents of notes.txt" and asked == []


def test_person_approves_through_the_client():
    async def steps(s):
        return await s.call_tool("pay_invoice", {"vendor": "Acme", "amount": 420})

    res, asked = run(steps, answer=True)
    assert not res.is_error and "paid 420" in text(res)
    assert len(asked) == 1 and "pay_invoice" in asked[0] and "high risk" in asked[0]


def test_person_declines_critical():
    async def steps(s):
        return await s.call_tool("run_sql", {"database": "app_production", "query": "DROP TABLE orders"})

    res, asked = run(steps, answer=False)
    assert res.is_error and "declined" in text(res) and "critical" in asked[0]


def test_client_without_approval_prompt_gets_a_clear_refusal():
    async def steps(s):
        return await s.call_tool("pay_invoice", {"vendor": "Acme", "amount": 420})

    res, _ = run(steps, answer=None)
    assert res.is_error and "a person must approve it" in text(res)


def test_blocked_by_checker_never_reaches_the_server(tmp_path):
    # run_sql with a destructive unscoped UPDATE is high risk; with the budget spent the checker blocks it
    pol = tmp_path / "p.yaml"
    from oversight.policies import DEFAULT_POLICY

    pol.write_text(DEFAULT_POLICY.read_text(encoding="utf-8").replace("max_interrupts_per_window: 6", "max_interrupts_per_window: 0"), encoding="utf-8")

    async def steps(s):
        return await s.call_tool("run_sql", {"database": "app", "query": "UPDATE customers SET email = NULL"})

    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "oversight.cli", "--policy", str(pol), "mcp", "--", sys.executable, str(TOY)])
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            return await steps(s)

    res = anyio.run(go)
    assert res.is_error and "was not run" in text(res) and "ran UPDATE" not in text(res)
