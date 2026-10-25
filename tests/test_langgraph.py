"""Runs a real LangGraph graph with a scripted model node, so no API key is needed."""

from typing import Annotated, TypedDict

import pytest

pytest.importorskip("langgraph")

from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402
from langchain_core.tools import tool as lc_tool  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402
from langgraph.graph.message import add_messages  # noqa: E402
from langgraph.prebuilt import ToolNode  # noqa: E402

from agent_regress import Case, Suite, expect  # noqa: E402
from agent_regress.integrations.langgraph import from_state, wrap  # noqa: E402


@lc_tool
def lookup_order(order_id: str) -> str:
    """Look up an order."""
    return f"order {order_id}: shipped"


@lc_tool
def issue_refund(order_id: str) -> str:
    """Refund an order."""
    raise ValueError("refunds are disabled")


class State(TypedDict):
    messages: Annotated[list, add_messages]


def model(state):
    usage = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
    if isinstance(state["messages"][-1], ToolMessage):
        return {"messages": [AIMessage(content="Order 42 has shipped.", usage_metadata=usage)]}
    calls = [{"name": "lookup_order", "args": {"order_id": "42"}, "id": "c1"}, {"name": "issue_refund", "args": {"order_id": "42"}, "id": "c2"}]
    return {"messages": [AIMessage(content="", tool_calls=calls, usage_metadata=usage)]}


def build():
    g = StateGraph(State)
    g.add_node("model", model)
    g.add_node("tools", ToolNode([lookup_order, issue_refund], handle_tool_errors=True))
    g.add_edge(START, "model")
    g.add_conditional_edges("model", lambda s: "tools" if s["messages"][-1].tool_calls else END, ["tools", END])
    g.add_edge("tools", "model")
    return g.compile(name="support graph")


def test_wrap_reads_tool_calls_errors_answer_and_usage():
    suite = Suite(wrap(build()), [Case("status", "Where is order 42?", [expect.calls("lookup_order", order_id="42"), expect.output_contains("shipped")])])
    result = suite.run()
    assert suite.name == "support_graph" and result.ok
    t = result.cases[0].runs[0].trajectory
    assert t.tools == ["lookup_order", "issue_refund"] and "shipped" in t.tool_calls[0].result
    assert t.tool_calls[1].error and "refunds are disabled" in t.tool_calls[1].error
    assert (t.llm_calls, t.input_tokens, t.output_tokens) == (2, 200, 40)


def test_returned_state_and_plain_message_lists():
    graph = build()
    r = Suite(lambda m: graph.invoke({"messages": [("user", m)]}), [Case("a", "x", [expect.calls("issue_refund")])], repeats=1).run()
    assert r.ok
    t = from_state([{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}])
    assert t.input == "hi" and t.output == "hello"
