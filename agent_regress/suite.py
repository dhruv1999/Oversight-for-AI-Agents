"""Cases, suites and results.

    suite = Suite(agent=my_agent, cases=[Case("refund", "Refund order 42", expect=[...])], repeats=3)
    result = suite.run()

`agent` is any function (plain or async) that takes the case input. It can return a Trajectory,
a plain string (tool calls are then taken from @tool decorated functions), or whatever your
framework returns: an OpenAI Agents SDK result, a LangGraph state, a list of Google ADK events or
Claude Agent SDK messages. See agent_regress.integrations for wrappers that do the running too.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .checks import Check, CheckResult
from .recording import _current
from .stats import wilson
from .trajectory import Trajectory


@dataclass
class Case:
    """One input and what the agent must and must not do with it."""

    name: str
    input: Any
    expect: list[Check] = field(default_factory=list)
    repeats: int | None = None  # overrides the suite's repeats for this case


@dataclass
class RunResult:
    attempt: int
    trajectory: Trajectory
    checks: list[CheckResult]

    @property
    def passed(self) -> bool:
        return self.trajectory.error is None and all(c.passed for c in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "passed": self.passed,
            "checks": [c.__dict__ for c in self.checks],
            "trajectory": self.trajectory.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RunResult:
        return cls(d["attempt"], Trajectory.from_dict(d["trajectory"]), [CheckResult(**c) for c in d["checks"]])


@dataclass
class CaseResult:
    name: str
    runs: list[RunResult]

    @property
    def n(self) -> int:
        return len(self.runs)

    @property
    def passes(self) -> int:
        return sum(r.passed for r in self.runs)

    @property
    def pass_rate(self) -> float:
        return self.passes / self.n if self.n else 0.0

    @property
    def interval(self) -> tuple[float, float]:
        return wilson(self.passes, self.n)

    @property
    def always_passes(self) -> bool:
        """pass^k: every run passed. The bar for anything a user relies on."""
        return self.n > 0 and self.passes == self.n

    @property
    def failing_checks(self) -> Counter[str]:
        """How many runs failed each check (crashes count under 'run crashed')."""
        counts: Counter[str] = Counter()
        for r in self.runs:
            if r.trajectory.error:
                counts["run crashed"] += 1
            for c in r.checks:
                if not c.passed:
                    counts[c.name] += 1
        return counts

    def example_failure(self, check: str) -> str:
        for r in self.runs:
            if check == "run crashed" and r.trajectory.error:
                return r.trajectory.error
            for c in r.checks:
                if c.name == check and not c.passed:
                    return c.detail
        return ""

    def mean(self, attr: str) -> float | None:
        values = [getattr(r.trajectory, attr) for r in self.runs]
        values = [v for v in values if v is not None]
        return sum(values) / len(values) if values else None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passes": self.passes, "n": self.n, "runs": [r.to_dict() for r in self.runs]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CaseResult:
        return cls(d["name"], [RunResult.from_dict(r) for r in d["runs"]])


@dataclass
class SuiteResult:
    name: str
    cases: list[CaseResult]
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    version: str = __version__

    @property
    def ok(self) -> bool:
        """Every run of every case passed."""
        return all(c.always_passes for c in self.cases)

    def case(self, name: str) -> CaseResult | None:
        return next((c for c in self.cases if c.name == name), None)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "created": self.created, "version": self.version, "cases": [c.to_dict() for c in self.cases]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SuiteResult:
        return cls(d["name"], [CaseResult.from_dict(c) for c in d["cases"]], d.get("created", ""), d.get("version", ""))

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=1), encoding="utf-8")
        return p

    @classmethod
    def load(cls, path: str | Path) -> SuiteResult:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


class Suite:
    """A set of cases for one agent, each run several times because agents are random."""

    def __init__(
        self,
        agent: Callable[[Any], Any],
        cases: Iterable[Case],
        repeats: int = 3,
        concurrency: int = 4,
        name: str | None = None,
        price_per_mtok: tuple[float, float] | None = None,
    ):
        """price_per_mtok: (input, output) USD per million tokens, used for cost when the framework
        reports tokens but not cost."""
        self.agent = agent
        self.cases = list(cases)
        if len({c.name for c in self.cases}) != len(self.cases):
            raise ValueError("case names must be unique; they are how results are compared")
        if repeats < 1 or concurrency < 1:
            raise ValueError("repeats and concurrency must be at least 1")
        self.repeats = repeats
        self.concurrency = concurrency
        self.name: str = str(name or getattr(agent, "__name__", "suite"))
        self.price_per_mtok = price_per_mtok

    def run(self, only: Iterable[str] | None = None, repeats: int | None = None) -> SuiteResult:
        """Run the suite and wait for it. Inside an event loop, use `await suite.arun()`."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun(only, repeats))
        raise RuntimeError("Suite.run() was called inside an event loop; use `await suite.arun()` instead")

    async def arun(self, only: Iterable[str] | None = None, repeats: int | None = None) -> SuiteResult:
        wanted = set(only) if only else None
        cases = [c for c in self.cases if wanted is None or c.name in wanted]
        if wanted and len(cases) != len(wanted):
            unknown = wanted - {c.name for c in cases}
            raise ValueError(f"unknown case names: {sorted(unknown)}")
        gate = asyncio.Semaphore(self.concurrency)

        async def one(case: Case, attempt: int) -> RunResult:
            async with gate:
                traj = await self._run_agent(case.input)
            self._fill_cost(traj)
            # off the event loop: a judge check calls a model, and should not stall the other runs
            checks = [] if traj.error else await asyncio.to_thread(lambda: [check(traj) for check in case.expect])
            return RunResult(attempt, traj, checks)

        per_case = [asyncio.gather(*(one(c, i + 1) for i in range(repeats or c.repeats or self.repeats))) for c in cases]
        runs = await asyncio.gather(*per_case)  # every run of every case shares the concurrency limit
        return SuiteResult(self.name, [CaseResult(c.name, list(r)) for c, r in zip(cases, runs, strict=True)])

    async def _run_agent(self, input: Any) -> Trajectory:
        from .integrations.auto import to_trajectory

        recorded = Trajectory(input=input, source="recorded")
        start = time.perf_counter()

        def call_sync() -> Any:
            token = _current.set(recorded)
            try:
                return self.agent(input)
            finally:
                _current.reset(token)

        async def call_async() -> Any:
            _current.set(recorded)  # this task has its own context, so this does not leak
            out = self.agent(input)
            return await out if inspect.isawaitable(out) else out

        try:
            if inspect.iscoroutinefunction(self.agent) or inspect.iscoroutinefunction(type(self.agent).__call__):
                out = await asyncio.create_task(call_async())
            else:
                out = await asyncio.to_thread(call_sync)
                if inspect.isawaitable(out):  # a plain function that returned a coroutine
                    out = await out
            traj = to_trajectory(out, input=input, recorded=recorded)
        except Exception as e:
            traj = recorded
            traj.error = f"{type(e).__name__}: {e}"
        if traj.latency_s is None:
            traj.latency_s = round(time.perf_counter() - start, 3)
        return traj

    def _fill_cost(self, traj: Trajectory) -> None:
        if traj.cost_usd is None and self.price_per_mtok and traj.total_tokens:
            pin, pout = self.price_per_mtok
            traj.cost_usd = (traj.input_tokens * pin + traj.output_tokens * pout) / 1_000_000
