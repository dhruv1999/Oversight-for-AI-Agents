"""A hand written tool loop on the Anthropic SDK. Needs ANTHROPIC_API_KEY.
The same pattern works with the OpenAI and Gemini SDKs: decorate tools with @tool and pass each
model response to record_response.     agent-ratchet run examples/frameworks/raw_sdk_suite.py"""

import anthropic

from agent_ratchet import Case, Suite, expect, judges, record_response, tool

client = anthropic.Anthropic()
TOOLS = [
    {
        "name": "lookup_order",
        "description": "Look up an order's status and amount.",
        "input_schema": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
    }
]


@tool
def lookup_order(order_id: str) -> str:
    return {"42": "shipped, $40", "77": "delivered, $900"}.get(order_id, "not found")


def support_agent(message: str) -> str:
    messages = [{"role": "user", "content": message}]
    while True:
        response = client.messages.create(model="claude-opus-5-5", max_tokens=1024, tools=TOOLS, messages=messages)
        record_response(response)
        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text")
        messages.append({"role": "assistant", "content": response.content})
        results = [{"type": "tool_result", "tool_use_id": b.id, "content": lookup_order(**b.input)} for b in response.content if b.type == "tool_use"]
        messages.append({"role": "user", "content": results})


suite = Suite(
    agent=support_agent,
    price_per_mtok=(5.0, 25.0),
    cases=[
        Case(
            "order status",
            "Where is order 42?",
            [
                expect.calls("lookup_order", order_id="42"),
                expect.judge("The reply tells the customer the order has shipped, in a friendly tone.", judges.anthropic()),
            ],
        ),
    ],
)
