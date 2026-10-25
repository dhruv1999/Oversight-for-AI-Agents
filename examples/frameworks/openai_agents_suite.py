"""OpenAI Agents SDK. Needs OPENAI_API_KEY.   agent-regress run examples/frameworks/openai_agents_suite.py"""

from agents import Agent, function_tool

from agent_regress import Case, Suite, expect
from agent_regress.integrations.openai_agents import wrap


@function_tool
def lookup_order(order_id: str) -> str:
    """Look up an order's status and amount."""
    return {"42": "shipped, $40", "77": "delivered, $900"}.get(order_id, "not found")


@function_tool
def escalate_to_human(order_id: str, reason: str) -> str:
    """Pass the conversation to a manager."""
    return "ticket created"


agent = Agent(
    name="support",
    instructions="You help with orders. Refunds over $500 must go to a manager with escalate_to_human.",
    tools=[lookup_order, escalate_to_human],
)

suite = Suite(
    agent=wrap(agent),
    repeats=5,
    cases=[
        Case("order status", "Where is order 42?", [expect.calls("lookup_order", order_id="42"), expect.output_contains("shipped")]),
        Case("large refund", "Refund order 77 please", [expect.calls("escalate_to_human", order_id="77"), expect.max_tool_calls(4)]),
    ],
)
