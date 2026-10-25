"""Runs the real OpenAI Agents SDK with a scripted model, so no API key is needed."""

import os

import pytest

os.environ.setdefault("OPENAI_AGENTS_DISABLE_TRACING", "1")
pytest.importorskip("agents")

from agents import Agent, Model, ModelResponse, Usage, function_tool  # noqa: E402
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText  # noqa: E402

from agent_regress import Case, Suite, expect  # noqa: E402
from agent_regress.integrations.openai_agents import wrap  # noqa: E402


@function_tool
def lookup_order(order_id: str) -> str:
    """Look up an order."""
    return f"order {order_id}: shipped"


@function_tool
def issue_refund(order_id: str) -> str:
    """Refund an order."""
    raise ValueError("refunds are disabled")


class Scripted(Model):
    """Calls lookup_order, then issue_refund, then answers."""

    async def get_response(self, system_instructions, input, *args, **kwargs):
        outputs = sum(1 for item in input if isinstance(item, dict) and item.get("type") == "function_call_output")
        if outputs < 2:
            name, args = [("lookup_order", '{"order_id": "42"}'), ("issue_refund", '{"order_id": "42"}')][outputs]
            out = [ResponseFunctionToolCall(type="function_call", id=f"fc{outputs}", call_id=f"c{outputs}", name=name, arguments=args, status="completed")]
        else:
            text = ResponseOutputText(type="output_text", text="Order 42 has shipped.", annotations=[])
            out = [ResponseOutputMessage(type="message", id="m1", role="assistant", status="completed", content=[text])]
        return ModelResponse(output=out, usage=Usage(requests=1, input_tokens=100, output_tokens=20, total_tokens=120), response_id=None)

    def stream_response(self, *args, **kwargs):
        raise NotImplementedError


def test_wrap_reads_tool_calls_errors_answer_and_usage():
    agent = Agent(name="support", instructions="help", tools=[lookup_order, issue_refund], model=Scripted())
    suite = Suite(
        wrap(agent),
        [Case("status", "Where is order 42?", [expect.calls_in_order("lookup_order", "issue_refund"), expect.output_contains("shipped")])],
        repeats=2,
    )
    result = suite.run()
    assert suite.name == "support" and result.ok
    t = result.cases[0].runs[0].trajectory
    assert t.source == "openai-agents"
    assert t.tool_calls[0].args == {"order_id": "42"} and "shipped" in t.tool_calls[0].result
    assert t.tool_calls[1].error and not expect.no_tool_errors()(t).passed
    assert (t.llm_calls, t.input_tokens, t.output_tokens) == (3, 300, 60)


def test_returned_run_result_is_detected():
    from agents import Runner

    agent = Agent(name="support", instructions="help", tools=[lookup_order, issue_refund], model=Scripted())

    async def my_agent(message):
        return await Runner.run(agent, message)

    assert Suite(my_agent, [Case("a", "x", [expect.calls("lookup_order", order_id="42")])], repeats=1).run().ok
