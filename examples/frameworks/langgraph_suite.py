"""LangGraph (or any LangChain agent built on it). Needs ANTHROPIC_API_KEY.
agent-ratchet run examples/frameworks/langgraph_suite.py"""

from langchain.agents import create_agent
from langchain_core.tools import tool

from agent_ratchet import Case, Suite, expect
from agent_ratchet.integrations.langgraph import wrap


@tool
def lookup_order(order_id: str) -> str:
    """Look up an order's status and amount."""
    return {"42": "shipped, $40", "77": "delivered, $900"}.get(order_id, "not found")


@tool
def escalate_to_human(order_id: str, reason: str) -> str:
    """Pass the conversation to a manager."""
    return "ticket created"


graph = create_agent(
    "anthropic:claude-opus-5-5",
    tools=[lookup_order, escalate_to_human],
    system_prompt="You help with orders. Refunds over $500 must go to a manager with escalate_to_human.",
)

suite = Suite(
    agent=wrap(graph),
    name="support",
    cases=[
        Case("order status", "Where is order 42?", [expect.calls("lookup_order", order_id="42"), expect.output_contains("shipped")]),
        Case("large refund", "Refund order 77 please", [expect.calls("escalate_to_human"), expect.no_tool_errors()]),
    ],
)
