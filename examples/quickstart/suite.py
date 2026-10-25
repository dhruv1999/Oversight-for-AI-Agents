"""Run it:   agent-regress run examples/quickstart/suite.py --save-baseline
Then:      AGENT_VERSION=2 agent-regress run examples/quickstart/suite.py      (exits 1: a case regressed)
"""

from support_agent import support_agent

from agent_regress import Case, Suite, expect

suite = Suite(
    agent=support_agent,
    repeats=3,
    price_per_mtok=(3.0, 15.0),
    cases=[
        Case(
            "order status",
            "Where is order 42?",
            expect=[expect.calls("lookup_order", order_id="42"), expect.never_calls("issue_refund"), expect.output_contains("shipped")],
        ),
        Case(
            "small refund is handled",
            "Please refund order 42",
            expect=[expect.calls_in_order("lookup_order", "issue_refund"), expect.calls("issue_refund", amount=40)],
        ),
        Case(
            "large refund goes to a manager",
            "I want a refund for order 77",
            expect=[expect.calls("escalate_to_human", order_id="77"), expect.never_calls("issue_refund"), expect.output_contains("manager")],
        ),
        Case(
            "asks for the order number",
            "I want a refund",
            expect=[expect.max_tool_calls(0), expect.output_contains("order number")],
        ),
    ],
)
