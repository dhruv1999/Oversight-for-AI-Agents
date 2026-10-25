"""OpenAI Agents SDK.

    from agent_ratchet.integrations.openai_agents import wrap
    suite = Suite(agent=wrap(my_agent), cases=[...])

or, if you run the agent yourself, return the RunResult and agent-ratchet reads it.
"""

from __future__ import annotations

from typing import Any

from ..trajectory import ToolCall, Trajectory
from ._util import as_args, as_text, get

ERROR_PREFIX = "An error occurred while running the tool"  # what the SDK returns to the model when a tool raises


def from_run_result(result: Any, input: Any = None) -> Trajectory:
    traj = Trajectory(input=input if input is not None else get(result, "input"), source="openai-agents")
    by_id: dict[str, ToolCall] = {}
    for item in get(result, "new_items", default=[]):
        kind = get(item, "type", default="")
        raw = get(item, "raw_item")
        if kind in ("tool_call_item", "handoff_call_item"):
            call = ToolCall(get(raw, "name", "type", default="tool"), as_args(get(raw, "arguments")), id=get(raw, "call_id", "id"))
            traj.tool_calls.append(call)
            if call.id:
                by_id[call.id] = call
        elif kind in ("tool_call_output_item", "handoff_output_item"):
            done = by_id.get(get(raw, "call_id", default=""))
            if done is not None:
                done.result = get(item, "output", default=get(raw, "output"))
                if isinstance(done.result, str) and done.result.startswith(ERROR_PREFIX):
                    done.error = done.result
    traj.output = as_text(get(result, "final_output"))
    usage = get(get(result, "context_wrapper"), "usage")
    if usage is not None:
        traj.llm_calls = get(usage, "requests", default=0)
        traj.input_tokens = get(usage, "input_tokens", default=0)
        traj.output_tokens = get(usage, "output_tokens", default=0)
    return traj


def wrap(agent: Any, **run_kwargs: Any) -> Any:
    """An async function that runs `agent` on one input with Runner.run and returns its Trajectory."""

    async def run(input: Any) -> Trajectory:
        from agents import Runner

        return from_run_result(await Runner.run(agent, input, **run_kwargs), input)

    run.__name__ = str(get(agent, "name", default="openai_agent"))
    return run
