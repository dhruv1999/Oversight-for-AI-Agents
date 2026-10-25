"""Turn a real run (for example a production trace) into a test case to edit and keep."""

from __future__ import annotations

from .checks import Check, calls, calls_in_order, no_tool_errors
from .suite import Case
from .trajectory import Trajectory


def snapshot(traj: Trajectory, name: str) -> Case:
    """A starting point: the same tools, in the same order, without errors. Tighten or loosen it by hand."""
    expect: list[Check] = [calls(t) for t in dict.fromkeys(traj.tools)]
    if len(traj.tools) > 1:
        expect.append(calls_in_order(*traj.tools))
    expect.append(no_tool_errors())
    return Case(name, traj.input, expect)


def case_code(traj: Trajectory, name: str) -> str:
    """The same starting point as Python code, ready to paste into a suite file."""
    lines = [f"Case({name!r},", f"     input={traj.input!r},", "     expect=["]
    for t in dict.fromkeys(traj.tools):
        lines.append(f"         expect.calls({t!r}),")
    if len(traj.tools) > 1:
        lines.append(f"         expect.calls_in_order({', '.join(map(repr, traj.tools))}),")
    lines.append("         expect.no_tool_errors(),")
    if traj.output:
        lines.append(f"         # the agent answered: {traj.output[:100]!r}")
    lines.append("     ]),")
    return "\n".join(lines)
