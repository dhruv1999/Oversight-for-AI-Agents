"""What one agent run did: the tools it called, what came back, the final answer and what it cost.

Every integration turns a framework's run into a Trajectory, so checks and reports work the same
way for every framework.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """One tool call, in the order the agent made it."""

    name: str
    args: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str | None = None  # set when the tool failed
    id: str | None = None


@dataclass
class Trajectory:
    """One run of an agent on one input."""

    input: Any = None
    output: str | None = None  # the final answer, as text
    tool_calls: list[ToolCall] = field(default_factory=list)
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None  # None when the framework does not report cost
    latency_s: float | None = None
    error: str | None = None  # set when the run itself crashed
    source: str = ""  # which integration produced this trajectory
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def tools(self) -> list[str]:
        """Names of the tools called, in order."""
        return [c.name for c in self.tool_calls]

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["input"] = _jsonable(self.input)
        d["meta"] = _jsonable(self.meta)
        d["tool_calls"] = [{**asdict(c), "args": _jsonable(c.args), "result": _jsonable(c.result)} for c in self.tool_calls]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Trajectory:
        calls = [ToolCall(**c) for c in d.get("tool_calls", [])]
        return cls(**{**{k: v for k, v in d.items() if k != "tool_calls"}, "tool_calls": calls})


def _jsonable(value: Any) -> Any:
    """Keep results saveable as JSON: anything unusual becomes its text form."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return str(value)


def text_of(content: Any) -> str:
    """Text from a message content that may be a string or a list of blocks."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(getattr(block, "text", "") or ""))
        return "".join(parts)
    return str(content)
