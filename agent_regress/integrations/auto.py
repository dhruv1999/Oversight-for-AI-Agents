"""Turn whatever an agent function returned into a Trajectory."""

from __future__ import annotations

from typing import Any

from ..trajectory import Trajectory


def to_trajectory(out: Any, input: Any = None, recorded: Trajectory | None = None) -> Trajectory:
    recorded = recorded if recorded is not None else Trajectory(input=input, source="recorded")
    if isinstance(out, Trajectory):
        if out.input is None:
            out.input = input
        if not out.tool_calls and recorded.tool_calls:
            out.tool_calls = recorded.tool_calls
        return out
    if out is None or isinstance(out, (str, int, float, bool)):
        recorded.output = None if out is None else str(out)
        return recorded
    if hasattr(out, "new_items") and hasattr(out, "final_output"):
        from .openai_agents import from_run_result

        return from_run_result(out, input)
    if isinstance(out, dict) and "messages" in out:
        from .langgraph import from_state

        return from_state(out, input)
    if isinstance(out, list) and out:
        first = out[0]
        if hasattr(first, "get_function_calls"):
            from .google_adk import from_events

            return from_events(out, input)
        if {type(m).__name__ for m in out} & {"AssistantMessage", "ResultMessage"}:
            from .claude_agent_sdk import from_messages

            return from_messages(out, input)
        if all(hasattr(m, "content") and hasattr(m, "type") for m in out):
            from .langgraph import from_state

            return from_state(out, input)
    if hasattr(out, "raw") and hasattr(out, "tasks_output"):  # CrewAI output without wrap(): no tool calls
        recorded.output = str(out.raw)
        recorded.source = "crewai"
        return recorded
    if isinstance(out, dict) and "output" in out:
        recorded.output = str(out["output"])
        return recorded
    recorded.output = str(out)
    return recorded
