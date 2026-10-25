"""Runs a real CrewAI crew with a scripted LLM, so no API key is needed."""

import importlib.util
import os

import pytest

if importlib.util.find_spec("crewai"):
    os.environ.update(CREWAI_DISABLE_TELEMETRY="true", CREWAI_TRACING_ENABLED="false")
pytest.importorskip("crewai")

from crewai import Agent, Crew, Task  # noqa: E402
from crewai.llms.base_llm import BaseLLM  # noqa: E402
from crewai.tools import tool as crew_tool  # noqa: E402

from agent_ratchet import Case, Suite, expect  # noqa: E402
from agent_ratchet.integrations.crewai import wrap  # noqa: E402


@crew_tool("lookup_order")
def lookup_order(order_id: str) -> str:
    """Look up an order by id."""
    return f"order {order_id}: shipped"


class Scripted(BaseLLM):
    def __init__(self):
        super().__init__(model="scripted")
        self.replies = [
            'Thought: I should look it up.\nAction: lookup_order\nAction Input: {"order_id": "42"}',
            "Thought: I know the answer.\nFinal Answer: Order 42 has shipped.",
        ]

    def call(self, messages, tools=None, callbacks=None, available_functions=None, from_task=None, from_agent=None, response_model=None):
        return self.replies.pop(0)

    def supports_function_calling(self):
        return False


def build(message):
    agent = Agent(role="support", goal="answer", backstory="helpful", tools=[lookup_order], llm=Scripted(), verbose=False)
    task = Task(description="{input}", expected_output="the order status", agent=agent)
    return Crew(agents=[agent], tasks=[task], verbose=False)


def test_wrap_reads_tool_calls_from_the_event_bus():
    checks = [expect.calls("lookup_order", order_id="42"), expect.output_contains("shipped")]
    suite = Suite(wrap(build), [Case("status", "Where is order 42?", checks)], repeats=2)
    result = suite.run()
    assert result.ok, [r.checks for r in result.cases[0].runs]
    t = result.cases[0].runs[0].trajectory
    assert t.source == "crewai" and t.tools == ["lookup_order"] and "shipped" in str(t.tool_calls[0].result)
