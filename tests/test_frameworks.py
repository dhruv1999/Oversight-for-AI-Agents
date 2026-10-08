"""The protect decorator inside real agent frameworks. Skipped when the framework is not installed;
the `frameworks` CI job installs them."""

import asyncio
import json

import pytest

from oversight import Oversight
from oversight.policy import PolicyError


def test_register_tool_changes_risk_and_validates():
    guard = Oversight(clock=lambda: 0.0)
    assert guard.check("read_report", {"name": "q3"}).risk == "high"  # unknown: cautious
    guard.register_tool("read_report", category="read", blast_radius="self")
    assert guard.check("read_report", {"name": "q3"}).allowed
    with pytest.raises(PolicyError):
        guard.register_tool("x", category="teleport")


def test_openai_agents_sdk():
    agents = pytest.importorskip("agents")
    from agents.tool_context import ToolContext

    from oversight.integrations.openai_agents import tool_error_message

    guard = Oversight(clock=lambda: 0.0)
    ran = []

    @agents.function_tool(failure_error_function=tool_error_message)
    @guard.protect()
    def pay_invoice(vendor: str, amount: float) -> str:
        """Pay an approved vendor invoice."""
        ran.append(amount)
        return "paid"

    assert pay_invoice.params_json_schema["required"] == ["vendor", "amount"]
    args = json.dumps({"vendor": "Acme", "amount": 420})
    out = asyncio.run(pay_invoice.on_invoke_tool(ToolContext(context=None, tool_name="pay_invoice", tool_call_id="t", tool_arguments=args), args))
    assert not ran and "pay_invoice was not run" in out  # refusal goes back to the model as text


def test_langchain():
    lc = pytest.importorskip("langchain_core.tools")
    from oversight import ActionBlocked

    guard = Oversight(clock=lambda: 0.0)

    @lc.tool
    @guard.protect(tool="read_file")
    def read_report(path: str) -> str:
        """Read a report."""
        return f"contents of {path}"

    @lc.tool
    @guard.protect()
    def pay_invoice(vendor: str, amount: float) -> str:
        """Pay an approved vendor invoice."""
        return "paid"

    assert read_report.args == {"path": {"title": "Path", "type": "string"}}
    assert read_report.invoke({"path": "a"}) == "contents of a"
    with pytest.raises(ActionBlocked):
        pay_invoice.invoke({"vendor": "Acme", "amount": 420})


def test_tool_error_message_only_reveals_oversight_refusals():
    from oversight import ActionBlocked
    from oversight.integrations.openai_agents import GENERIC, tool_error_message

    check = Oversight(clock=lambda: 0.0).check("pay_invoice", {"vendor": "Acme", "amount": 420})
    refusal = ActionBlocked(check)
    assert tool_error_message(None, refusal).startswith("pay_invoice was not run")
    try:
        try:
            raise refusal
        except ActionBlocked as inner:
            raise RuntimeError("wrapped by the framework") from inner
    except RuntimeError as wrapped:
        assert tool_error_message(None, wrapped).startswith("pay_invoice was not run")
    assert tool_error_message(None, ValueError("db password is hunter2")) == GENERIC
