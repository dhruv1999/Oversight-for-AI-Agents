"""CrewAI.

    from agent_regress.integrations.crewai import wrap
    suite = Suite(agent=wrap(build_crew), cases=[...])   # build_crew(input) returns a fresh Crew

Tool calls are not part of a crew's output, so wrap() listens on CrewAI's event bus during the
run. Runs are serialised because that event bus is shared by the whole process.
"""

from __future__ import annotations

import threading
from typing import Any

from ..trajectory import ToolCall, Trajectory
from ._util import as_args, get

_lock = threading.Lock()


def wrap(crew: Any, input_key: str = "input") -> Any:
    """A function that kicks off the crew with inputs={input_key: input} and returns its Trajectory.
    `crew` is a Crew, or a function that builds a fresh Crew for each input (recommended)."""

    def run(input: Any) -> Trajectory:
        from crewai.events import ToolUsageErrorEvent, ToolUsageFinishedEvent, crewai_event_bus

        traj = Trajectory(input=input, source="crewai")
        with _lock, crewai_event_bus.scoped_handlers():

            @crewai_event_bus.on(ToolUsageFinishedEvent)
            def finished(source: Any, event: Any) -> None:
                traj.tool_calls.append(ToolCall(event.tool_name, as_args(event.tool_args), result=event.output))

            @crewai_event_bus.on(ToolUsageErrorEvent)
            def failed(source: Any, event: Any) -> None:
                traj.tool_calls.append(ToolCall(event.tool_name, as_args(event.tool_args), error=str(event.error)))

            c = crew if hasattr(crew, "kickoff") else crew(input)
            out = c.kickoff(inputs={input_key: input})
            if hasattr(crewai_event_bus, "flush"):
                crewai_event_bus.flush()
        traj.output = get(out, "raw", default=str(out))
        usage = get(out, "token_usage")
        if usage is not None:
            traj.input_tokens = get(usage, "prompt_tokens", default=0)
            traj.output_tokens = get(usage, "completion_tokens", default=0)
            traj.llm_calls = get(usage, "successful_requests", default=0)
        return traj

    run.__name__ = "crew"
    return run
