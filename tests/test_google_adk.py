"""Runs a real Google ADK agent with a scripted model, so no API key is needed."""

from collections.abc import AsyncGenerator

import pytest

pytest.importorskip("google.adk")

from google.adk.agents import LlmAgent  # noqa: E402
from google.adk.models import BaseLlm, LlmResponse  # noqa: E402
from google.genai import types  # noqa: E402

from agent_regress import Case, Suite, expect  # noqa: E402
from agent_regress.integrations.google_adk import wrap  # noqa: E402


class Scripted(BaseLlm):
    model: str = "scripted"

    async def generate_content_async(self, llm_request, stream=False) -> AsyncGenerator[LlmResponse, None]:
        usage = types.GenerateContentResponseUsageMetadata(prompt_token_count=100, candidates_token_count=20, total_token_count=120)
        answered = any(p.function_response for c in llm_request.contents for p in (c.parts or []))
        if not answered:
            call = types.FunctionCall(id="c1", name="lookup_order", args={"order_id": "42"})
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(function_call=call)]), usage_metadata=usage)
        else:
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text="Order 42 has shipped.")]), usage_metadata=usage)


def lookup_order(order_id: str) -> str:
    """Look up an order."""
    return f"order {order_id}: shipped"


def test_wrap_reads_tool_calls_answer_and_usage():
    agent = LlmAgent(name="support", model=Scripted(), instruction="help", tools=[lookup_order])
    suite = Suite(wrap(agent), [Case("status", "Where is order 42?", [expect.calls("lookup_order", order_id="42"), expect.output_contains("shipped")])])
    result = suite.run()
    assert suite.name == "support" and result.ok, result.cases[0].runs[0]
    t = result.cases[0].runs[0].trajectory
    assert t.source == "google-adk" and t.tool_calls[0].result == "order 42: shipped"
    assert (t.llm_calls, t.input_tokens, t.output_tokens) == (2, 200, 40)
