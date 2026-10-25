"""LangGraph (and LangChain agents built on it).

    from agent_regress.integrations.langgraph import wrap
    suite = Suite(agent=wrap(graph), cases=[...])

or return the state from graph.invoke(...) yourself; any state with a "messages" list works.
"""

from __future__ import annotations

from typing import Any

from ..trajectory import ToolCall, Trajectory, text_of
from ._util import as_args, get


def _kind(m: Any) -> str:
    kind = get(m, "type", "role", default="")
    return {"assistant": "ai", "user": "human"}.get(kind, kind)


def from_state(state: Any, input: Any = None) -> Trajectory:
    messages = state["messages"] if isinstance(state, dict) else list(state)
    traj = Trajectory(input=input, source="langgraph")
    by_id: dict[str, ToolCall] = {}
    for m in messages:
        kind = _kind(m)
        if kind == "human" and traj.input is None:
            traj.input = text_of(get(m, "content"))
        elif kind == "ai":
            traj.llm_calls += 1
            usage = get(m, "usage_metadata")
            if usage:
                traj.input_tokens += get(usage, "input_tokens", default=0)
                traj.output_tokens += get(usage, "output_tokens", default=0)
            for tc in get(m, "tool_calls", default=[]) or []:
                call = ToolCall(get(tc, "name", default="tool"), as_args(get(tc, "args")), id=get(tc, "id"))
                traj.tool_calls.append(call)
                if call.id:
                    by_id[call.id] = call
            if not get(m, "tool_calls"):
                traj.output = text_of(get(m, "content"))
        elif kind == "tool":
            done = by_id.get(get(m, "tool_call_id", default=""))
            if done is not None:
                done.result = text_of(get(m, "content"))
                if get(m, "status") == "error":
                    done.error = done.result
    return traj


def wrap(graph: Any, config: Any = None) -> Any:
    """A function that sends the input as a user message to a compiled graph and returns its Trajectory."""

    def run(input: Any) -> Trajectory:
        state = graph.invoke({"messages": [{"role": "user", "content": str(input)}]}, config)
        return from_state(state, input)

    run.__name__ = str(get(graph, "name", default="langgraph_agent")).replace(" ", "_")
    return run
