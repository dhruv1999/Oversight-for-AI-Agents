"""Record tool calls from any Python agent, including hand written loops on the OpenAI,
Anthropic or Gemini SDKs.

    from agent_regress import tool, record_usage

    @tool
    def lookup_order(order_id: str) -> str: ...

Inside a test run, every call to a decorated tool is added to the run's trajectory. Outside a
test run the decorator does nothing, so it is safe to leave in production code.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, TypeVar, overload

from .trajectory import ToolCall, Trajectory

F = TypeVar("F", bound=Callable[..., Any])
_current: ContextVar[Trajectory | None] = ContextVar("agent_regress_trajectory", default=None)


def current() -> Trajectory | None:
    """The trajectory being recorded right now, if any."""
    return _current.get()


@contextmanager
def recording(input: Any = None) -> Iterator[Trajectory]:
    """Record decorated tool calls and usage into a fresh trajectory for the duration of the block."""
    traj = Trajectory(input=input, source="recorded")
    token = _current.set(traj)
    try:
        yield traj
    finally:
        _current.reset(token)


def record_usage(input_tokens: int = 0, output_tokens: int = 0, cost_usd: float | None = None, llm_calls: int = 1) -> None:
    """Add one model call's usage to the current run. Does nothing outside a test run."""
    traj = _current.get()
    if traj is None:
        return
    traj.llm_calls += llm_calls
    traj.input_tokens += input_tokens
    traj.output_tokens += output_tokens
    if cost_usd is not None:
        traj.cost_usd = (traj.cost_usd or 0.0) + cost_usd


@overload
def tool(fn: F) -> F: ...
@overload
def tool(*, name: str | None = None) -> Callable[[F], F]: ...
def tool(fn: Any = None, *, name: str | None = None) -> Any:
    """Decorator that records every call of a tool function while a test run is active."""

    def decorate(f: F) -> F:
        tool_name = name or f.__name__
        sig = inspect.signature(f)

        def start(args: tuple[Any, ...], kwargs: dict[str, Any]) -> ToolCall | None:
            traj = _current.get()
            if traj is None:
                return None
            try:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                params = {k: v for k, v in bound.arguments.items() if k not in ("self", "cls")}
            except TypeError:
                params = {"args": list(args), **kwargs}
            call = ToolCall(tool_name, params)
            traj.tool_calls.append(call)
            return call

        if inspect.iscoroutinefunction(f):

            @functools.wraps(f)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                call = start(args, kwargs)
                try:
                    result = await f(*args, **kwargs)
                except Exception as e:
                    if call:
                        call.error = f"{type(e).__name__}: {e}"
                    raise
                if call:
                    call.result = result
                return result

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            call = start(args, kwargs)
            try:
                result = f(*args, **kwargs)
            except Exception as e:
                if call:
                    call.error = f"{type(e).__name__}: {e}"
                raise
            if call:
                call.result = result
            return result

        return wrapper  # type: ignore[return-value]

    return decorate(fn) if fn is not None else decorate


def record_response(response: Any) -> None:
    """Record a model response's token usage, from the OpenAI, Anthropic or Gemini SDKs.

    Use it in a hand written agent loop: `record_response(client.messages.create(...))`.
    """
    usage = getattr(response, "usage", None)
    if usage is not None:
        inp = getattr(usage, "input_tokens", None)  # Anthropic, OpenAI Responses API
        if inp is None:
            inp = getattr(usage, "prompt_tokens", 0)  # OpenAI Chat Completions
        out = getattr(usage, "output_tokens", None)
        if out is None:
            out = getattr(usage, "completion_tokens", 0)
        record_usage(int(inp or 0), int(out or 0))
        return
    meta = getattr(response, "usage_metadata", None)  # Gemini
    if meta is not None:
        thoughts = getattr(meta, "thoughts_token_count", 0) or 0
        record_usage(int(getattr(meta, "prompt_token_count", 0) or 0), int(getattr(meta, "candidates_token_count", 0) or 0) + int(thoughts))
        return
    record_usage()
