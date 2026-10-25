"""Claude Agent SDK.

    from agent_regress.integrations.claude_agent_sdk import wrap
    suite = Suite(agent=wrap(ClaudeAgentOptions(...)), cases=[...])

or collect the messages from query(...) yourself and return the list.
"""

from __future__ import annotations

from typing import Any

from ..trajectory import ToolCall, Trajectory, text_of
from ._util import get


def from_messages(messages: list[Any], input: Any = None) -> Trajectory:
    traj = Trajectory(input=input, source="claude-agent-sdk")
    by_id: dict[str, ToolCall] = {}
    last_text = None
    for m in messages:
        kind = type(m).__name__
        if kind == "AssistantMessage":
            traj.llm_calls += 1
            texts = []
            for block in get(m, "content", default=[]) or []:
                bkind = type(block).__name__
                if bkind == "ToolUseBlock":
                    call = ToolCall(block.name, dict(block.input or {}), id=block.id)
                    traj.tool_calls.append(call)
                    by_id[block.id] = call
                elif bkind == "TextBlock":
                    texts.append(block.text)
            if texts:
                last_text = "".join(texts)
        elif kind == "UserMessage" and isinstance(get(m, "content"), list):
            for block in m.content:
                if type(block).__name__ == "ToolResultBlock" and block.tool_use_id in by_id:
                    call = by_id[block.tool_use_id]
                    call.result = text_of(block.content)
                    if block.is_error:
                        call.error = call.result or "tool failed"
        elif kind == "ResultMessage":
            traj.output = get(m, "result", default=last_text)
            traj.cost_usd = get(m, "total_cost_usd")
            usage = get(m, "usage") or {}
            traj.input_tokens = get(usage, "input_tokens", default=traj.input_tokens)
            traj.output_tokens = get(usage, "output_tokens", default=traj.output_tokens)
            traj.llm_calls = get(m, "num_turns", default=traj.llm_calls)
            if get(m, "is_error"):
                traj.error = f"agent run ended with an error ({get(m, 'subtype', default='error')})"
    if traj.output is None:
        traj.output = last_text
    return traj


def wrap(options: Any = None) -> Any:
    """An async function that runs query(prompt=input, options=options) and returns its Trajectory."""

    async def run(input: Any) -> Trajectory:
        from claude_agent_sdk import query

        return from_messages([m async for m in query(prompt=str(input), options=options)], input)

    run.__name__ = "claude_agent"
    return run
