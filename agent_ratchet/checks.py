"""Checks: what an agent run must and must not do.

    from agent_ratchet import expect

    expect.calls("lookup_order", order_id="42")
    expect.never_calls("issue_refund")
    expect.calls_in_order("lookup_order", "escalate")
    expect.output_contains("refund")
    expect.max_tool_calls(5)

Each check takes a Trajectory and returns a CheckResult. Checks are plain functions of the run,
with no model calls, so they are free, fast and give the same answer every time. For judgement
calls, `expect.judge` asks a model (see agent_ratchet.judges).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .trajectory import ToolCall, Trajectory


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class Check:
    """A named rule about a run. Call it with a Trajectory to get a CheckResult."""

    name: str
    fn: Callable[[Trajectory], tuple[bool, str]]

    def __call__(self, traj: Trajectory) -> CheckResult:
        try:
            passed, detail = self.fn(traj)
        except Exception as e:  # a broken check fails; it never passes silently
            return CheckResult(self.name, False, _short(f"check raised {type(e).__name__}: {e}"))
        return CheckResult(self.name, bool(passed), _short(str(detail)))


def _short(detail: str, limit: int = 300) -> str:
    return detail if len(detail) <= limit else detail[: limit - 3] + "..."


def _describe(value: Any) -> str:
    if isinstance(value, re.Pattern):
        return f"/{value.pattern}/"
    if isinstance(value, type):
        return f"any {value.__name__}"
    if callable(value):
        return getattr(value, "__name__", "a condition")
    return repr(value)


def _matches(expected: Any, actual: Any) -> bool:
    if isinstance(expected, re.Pattern):
        return actual is not None and expected.search(str(actual)) is not None
    if isinstance(expected, type):
        return isinstance(actual, expected)
    if callable(expected):
        return bool(expected(actual))
    return bool(expected == actual)


def _args_match(call: ToolCall, expected: dict[str, Any]) -> bool:
    return all(k in call.args and _matches(v, call.args[k]) for k, v in expected.items())


def calls(tool: str, *, times: int | None = None, at_least: int = 1, **args: Any) -> Check:
    """The agent calls `tool`, optionally with matching arguments.

    Argument values can be exact values, compiled regular expressions, types (any value of that
    type), or functions that return True for an acceptable value. `times` asks for an exact count; `at_least` for a minimum.
    """
    shown = ", ".join(f"{k}={_describe(v)}" for k, v in args.items())
    name = f"calls {tool}({shown})" + (f" {times} times" if times is not None else "")

    def fn(t: Trajectory) -> tuple[bool, str]:
        hits = [c for c in t.tool_calls if c.name == tool and _args_match(c, args)]
        ok = len(hits) == times if times is not None else len(hits) >= at_least
        if ok:
            return True, ""
        same_tool = [c.args for c in t.tool_calls if c.name == tool]
        if same_tool and args:
            return False, f"called {tool} with {same_tool[0]}"
        return False, f"called {len(hits)} times" if hits else f"never called {tool}; called {t.tools or 'no tools'}"

    return Check(name, fn)


def _need_tools(check: str, tools: tuple[str, ...]) -> None:
    if not tools:
        raise ValueError(f"expect.{check}() needs at least one tool name")


def never_calls(*tools: str) -> Check:
    """The agent never calls any of these tools."""
    _need_tools("never_calls", tools)

    def fn(t: Trajectory) -> tuple[bool, str]:
        bad = [n for n in t.tools if n in tools]
        return (not bad, f"called {', '.join(dict.fromkeys(bad))}" if bad else "")

    return Check(f"never calls {', '.join(tools)}", fn)


def only_calls(*tools: str) -> Check:
    """Every tool the agent calls is one of these."""
    _need_tools("only_calls", tools)

    def fn(t: Trajectory) -> tuple[bool, str]:
        extra = [n for n in t.tools if n not in tools]
        return (not extra, f"also called {', '.join(dict.fromkeys(extra))}" if extra else "")

    return Check(f"only calls {', '.join(tools)}", fn)


def calls_in_order(*tools: str) -> Check:
    """These tools are called in this order (other calls may happen in between)."""
    _need_tools("calls_in_order", tools)

    def fn(t: Trajectory) -> tuple[bool, str]:
        i = 0
        for n in t.tools:
            if i < len(tools) and n == tools[i]:
                i += 1
        return (i == len(tools), "" if i == len(tools) else f"order was {t.tools}")

    return Check(f"calls {' then '.join(tools)}", fn)


def no_tool_errors() -> Check:
    """No tool call failed."""

    def fn(t: Trajectory) -> tuple[bool, str]:
        failed = [f"{c.name}: {c.error}" for c in t.tool_calls if c.error]
        return (not failed, "; ".join(failed))

    return Check("no tool errors", fn)


def output_contains(*texts: str, case_sensitive: bool = False) -> Check:
    """The final answer contains every one of these texts."""

    def fn(t: Trajectory) -> tuple[bool, str]:
        out = t.output or ""
        hay = out if case_sensitive else out.lower()
        missing = [x for x in texts if (x if case_sensitive else x.lower()) not in hay]
        return (not missing, f"missing {missing}; answer was {out[:120]!r}" if missing else "")

    return Check(f"answer contains {', '.join(map(repr, texts))}", fn)


def output_not_contains(*texts: str, case_sensitive: bool = False) -> Check:
    """The final answer contains none of these texts."""

    def fn(t: Trajectory) -> tuple[bool, str]:
        out = t.output or ""
        hay = out if case_sensitive else out.lower()
        found = [x for x in texts if (x if case_sensitive else x.lower()) in hay]
        return (not found, f"contains {found}" if found else "")

    return Check(f"answer avoids {', '.join(map(repr, texts))}", fn)


def output_matches(pattern: str | re.Pattern[str]) -> Check:
    """The final answer matches a regular expression."""
    rx = re.compile(pattern) if isinstance(pattern, str) else pattern

    def fn(t: Trajectory) -> tuple[bool, str]:
        ok = rx.search(t.output or "") is not None
        return (ok, "" if ok else f"answer was {(t.output or '')[:120]!r}")

    return Check(f"answer matches /{rx.pattern}/", fn)


def _at_most(label: str, limit: float, value: Callable[[Trajectory], float | None], unit: str = "") -> Check:
    def fn(t: Trajectory) -> tuple[bool, str]:
        v = value(t)
        if v is None:
            return False, f"{label} was not reported by this integration"
        return (v <= limit, f"{label} was {v:g}{unit}")

    return Check(f"{label} at most {limit:g}{unit}", fn)


def max_tool_calls(n: int) -> Check:
    return _at_most("tool calls", n, lambda t: len(t.tool_calls))


def max_llm_calls(n: int) -> Check:
    return _at_most("model calls", n, lambda t: t.llm_calls)


def max_tokens(n: int) -> Check:
    return _at_most("tokens", n, lambda t: t.total_tokens)


def max_cost(usd: float) -> Check:
    """Fails when cost is unknown: give the Suite a price, or use an integration that reports cost."""
    return _at_most("cost", usd, lambda t: t.cost_usd, " USD")


def max_latency(seconds: float) -> Check:
    return _at_most("latency", seconds, lambda t: t.latency_s, " s")


def check(fn: Callable[[Trajectory], Any], name: str | None = None) -> Check:
    """Your own rule: a function of the trajectory returning True/False, or (passed, detail)."""

    def wrapped(t: Trajectory) -> tuple[bool, str]:
        r = fn(t)
        return (bool(r[0]), str(r[1])) if isinstance(r, tuple) else (bool(r), "")

    return Check(str(name or getattr(fn, "__name__", "custom check")), wrapped)


def judge(rubric: str, llm: Callable[[str], str], name: str | None = None) -> Check:
    """A model grades the run against a rubric. See agent_ratchet.judges for ready made graders."""
    from .judges import judge as _judge

    return _judge(rubric, llm, name)
