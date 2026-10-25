"""Google Agent Development Kit (ADK).

    from agent_regress.integrations.google_adk import wrap
    suite = Suite(agent=wrap(root_agent), cases=[...])

or collect the events from runner.run_async(...) yourself and return the list.
"""

from __future__ import annotations

from typing import Any

from ..trajectory import ToolCall, Trajectory
from ._util import get


def from_events(events: list[Any], input: Any = None) -> Trajectory:
    traj = Trajectory(input=input, source="google-adk")
    by_id: dict[str, ToolCall] = {}
    final: list[str] = []
    for e in events:
        if get(e, "partial"):
            continue
        usage = get(e, "usage_metadata")
        if usage is not None:
            traj.llm_calls += 1
            traj.input_tokens += get(usage, "prompt_token_count", default=0)
            traj.output_tokens += get(usage, "candidates_token_count", default=0) + get(usage, "thoughts_token_count", default=0)
        for fc in e.get_function_calls():
            call = ToolCall(fc.name or "tool", dict(fc.args or {}), id=fc.id)
            traj.tool_calls.append(call)
            if call.id:
                by_id[call.id] = call
        for fr in e.get_function_responses():
            done = by_id.get(fr.id or "") or next((c for c in reversed(traj.tool_calls) if c.name == fr.name and c.result is None), None)
            if done is None:
                continue
            response = fr.response or {}
            done.result = response.get("result", response) if isinstance(response, dict) else response
            if isinstance(response, dict) and response.get("error"):
                done.error = str(response["error"])
        if e.is_final_response() and e.content and e.content.parts:
            final.extend(p.text for p in e.content.parts if getattr(p, "text", None) and not getattr(p, "thought", False))
    traj.output = "".join(final) or None
    return traj


def wrap(agent: Any, app_name: str = "agent_regress", user_id: str = "agent-regress") -> Any:
    """An async function that runs `agent` in a fresh in-memory session and returns its Trajectory."""

    async def run(input: Any) -> Trajectory:
        from google.adk.runners import InMemoryRunner
        from google.genai import types

        runner = InMemoryRunner(agent=agent, app_name=app_name)
        session = await runner.session_service.create_session(app_name=app_name, user_id=user_id)
        message = types.Content(role="user", parts=[types.Part(text=str(input))])
        events = [e async for e in runner.run_async(user_id=user_id, session_id=session.id, new_message=message)]
        return from_events(events, input)

    run.__name__ = str(get(agent, "name", default="adk_agent"))
    return run
