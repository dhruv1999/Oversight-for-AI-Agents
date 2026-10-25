"""A tiny customer support agent for the quickstart. No API key needed: the "model" is a few
if statements, so you can see agent-ratchet catch a regression in seconds.

Set AGENT_VERSION=2 to simulate a prompt change that quietly breaks one behaviour: version 2
refunds large orders itself instead of passing them to a manager.
"""

import os
import re

from agent_ratchet import record_usage, tool

ORDERS = {"42": {"status": "shipped", "amount": 40}, "77": {"status": "delivered", "amount": 900}}


@tool
def lookup_order(order_id: str) -> dict:
    return ORDERS[order_id]


@tool
def issue_refund(order_id: str, amount: float) -> str:
    return f"refunded {amount} for order {order_id}"


@tool
def escalate_to_human(order_id: str, reason: str) -> str:
    return "ticket created"


def support_agent(message: str) -> str:
    record_usage(input_tokens=350, output_tokens=60)  # what a real model call would report
    version = os.environ.get("AGENT_VERSION", "1")
    match = re.search(r"order (\d+)", message)
    if not match:
        return "Happy to help. What is your order number?"
    order_id = match.group(1)
    order = lookup_order(order_id)
    if "refund" not in message.lower():
        return f"Order {order_id} is {order['status']}."
    if order["amount"] > 500 and version == "1":
        escalate_to_human(order_id, reason=f"refund of ${order['amount']}")
        return f"Refunds over $500 need a manager, so I've passed order {order_id} to one. You'll hear back within a day."
    issue_refund(order_id, order["amount"])
    return f"Done: ${order['amount']} refunded for order {order_id}."
