"""Cases, suites and results.

    suite = Suite(agent=my_agent, cases=[Case("refund", "Refund order 42", expect=[...])])
    result = suite.run()

`agent` is any function (plain or async) that takes the case input. It can return a Trajectory,
a plain string (tool calls are then taken from @tool decorated functions), or whatever your
framework returns: an OpenAI Agents SDK result, a LangGraph state, a list of Google ADK events or
Claude Agent SDK messages. See agent_ratchet.integrations for wrappers that do the running too.
"""

from __future__ import annotations

import asyncio
import contextvars
import dataclasses
import functools
import hashlib
import inspect
import json
import re
import threading
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
from .trajectory import Trajectory

FORMAT = 1  # version of the saved result files
DEFAULT_DIR = Path(".agent-ratchet")
RETRY_DELAY_S = 1.0  # first wait before retrying a run that hit a provider error; doubles each time

# provider errors that say "try again", not "the agent is wrong"
TRANSIENT_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}
TRANSIENT_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "DeadlineExceeded",
    "InternalServerError",
    "OverloadedError",
    "RateLimitError",
    "ResourceExhausted",
    "ServiceUnavailable",
    "ServiceUnavailableError",
}


def slug(name: str) -> str:
    """A suite name that is safe as a file name."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "suite"


def baseline_path(suite_name: str, directory: str | Path = DEFAULT_DIR) -> Path:
    """Where a suite's baseline lives unless you say otherwise."""
    return Path(directory) / f"{slug(suite_name)}.baseline.json"


@dataclass
class Case:
    """One input and what the agent must and must not do with it."""

    name: str
    input: Any
    expect: list[Check] = field(default_factory=list)
    repeats: int | None = None  # overrides the suite's repeats for this case
    must_pass: bool = False  # any failed run fails the build, whatever the baseline says

    @property
    def fingerprint(self) -> str:
        """Changes when the input or the checks change, so an edited case is not compared with an old baseline."""
        try:
            shown = json.dumps(self.input, sort_keys=True, default=repr)
        except (TypeError, ValueError):
            shown = repr(self.input)
        text = shown + "\n" + "\n".join(c.name for c in self.expect)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


@dataclass
class RunResult:
    attempt: int
    trajectory: Trajectory
    checks: list[CheckResult]

    @property
    def passed(self) -> bool:
        return self.trajectory.error is None and all(c.passed for c in self.checks)

    def to_dict(self, full: bool = True) -> dict[str, Any]:
        """full=False keeps only what a comparison needs: check names, pass or fail, and metrics.
        No inputs, answers or tool data, so the file is safe to commit."""
        t = self.trajectory
        if full:
            checks = [dataclasses.asdict(c) for c in self.checks]
            return {"attempt": self.attempt, "passed": self.passed, "checks": checks, "trajectory": t.to_dict()}
        metrics = {k: getattr(t, k) for k in ("llm_calls", "input_tokens", "output_tokens", "cost_usd", "latency_s")}
        error = t.error.split(":")[0] if t.error else None  # the kind of error, not its message
        checks = [{"name": c.name, "passed": c.passed} for c in self.checks]
        return {"attempt": self.attempt, "passed": self.passed, "checks": checks, "trajectory": {"error": error, **metrics}}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RunResult:
        return cls(d["attempt"], Trajectory.from_dict(d["trajectory"]), [CheckResult(**c) for c in d["checks"]])


@dataclass
class CaseResult:
    name: str
    runs: list[RunResult]
    must_pass: bool = False
    fingerprint: str | None = None

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
    def always_passes(self) -> bool:
        """pass^k: every run passed. The bar for anything a user relies on."""
        return self.n > 0 and self.passes == self.n

    @property
    def must_pass_failed(self) -> bool:
        return self.must_pass and not self.always_passes

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

    def to_dict(self, full: bool = True) -> dict[str, Any]:
        return {
            "name": self.name,
            "passes": self.passes,
            "n": self.n,
            "must_pass": self.must_pass,
            "fingerprint": self.fingerprint,
            "runs": [r.to_dict(full) for r in self.runs],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CaseResult:
        return cls(d["name"], [RunResult.from_dict(r) for r in d["runs"]], d.get("must_pass", False), d.get("fingerprint"))


@dataclass
class SuiteResult:
    name: str
    cases: list[CaseResult]
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    version: str = __version__
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Every run of every case passed."""
        return all(c.always_passes for c in self.cases)

    @property
    def must_pass_failures(self) -> list[CaseResult]:
        return [c for c in self.cases if c.must_pass_failed]

    @property
    def cost_usd(self) -> float | None:
        costs = [r.trajectory.cost_usd for c in self.cases for r in c.runs if r.trajectory.cost_usd is not None]
        return sum(costs) if costs else None

    def case(self, name: str) -> CaseResult | None:
        return next((c for c in self.cases if c.name == name), None)

    def subset(self, names: Iterable[str]) -> SuiteResult:
        wanted = set(names)
        return dataclasses.replace(self, cases=[c for c in self.cases if c.name in wanted])

    def merged(self, newer: SuiteResult) -> SuiteResult:
        """This result with the cases in `newer` replaced or added: saving a partial run keeps the other cases."""
        fresh = {c.name: c for c in newer.cases}
        kept = [fresh.pop(c.name, c) for c in self.cases]
        return dataclasses.replace(newer, cases=kept + list(fresh.values()), meta={**self.meta, **newer.meta})

    def to_dict(self, full: bool = True) -> dict[str, Any]:
        return {
            "format": FORMAT,
            "name": self.name,
            "created": self.created,
            "version": self.version,
            "meta": self.meta,
            "cases": [c.to_dict(full) for c in self.cases],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SuiteResult:
        if d.get("format", 1) > FORMAT:
            raise ValueError(f"this result was saved by a newer version of agent-ratchet ({d.get('version')}); upgrade to read it")
        return cls(d["name"], [CaseResult.from_dict(c) for c in d["cases"]], d.get("created", ""), d.get("version", ""), d.get("meta", {}))

    def save(self, path: str | Path, full: bool = True) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(full), indent=1), encoding="utf-8")
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
        max_repeats: int = 10,
        concurrency: int = 4,
        timeout: float | None = 300.0,
        retries: int = 2,
        name: str | None = None,
        price_per_mtok: tuple[float, float] | None = None,
    ):
        """
        repeats: runs per case on every check.
        max_repeats: runs per case when saving a baseline, and the most a case gets when it looks
            worse than the baseline and needs more runs to tell a real drop from bad luck.
        timeout: seconds before a run is stopped and counted as failed (None waits forever).
        retries: extra attempts for a run that hits a provider error such as a rate limit.
        price_per_mtok: (input, output) USD per million tokens, used for cost when the framework
            reports tokens but not cost.
        """
        self.agent = agent
        self.cases = list(cases)
        if len({c.name for c in self.cases}) != len(self.cases):
            raise ValueError("case names must be unique; they are how results are compared")
        if repeats < 1 or concurrency < 1 or retries < 0:
            raise ValueError("repeats and concurrency must be at least 1, retries at least 0")
        if max_repeats < repeats:
            raise ValueError("max_repeats must be at least repeats")
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive, or None")
        self.repeats = repeats
        self.max_repeats = max_repeats
        self.concurrency = concurrency
        self.timeout = timeout
        self.retries = retries
        self.name: str = str(name or getattr(agent, "__name__", "suite"))
        self.price_per_mtok = price_per_mtok
        self._is_async = inspect.iscoroutinefunction(agent) or inspect.iscoroutinefunction(type(agent).__call__)

    def run(
        self,
        only: Iterable[str] | None = None,
        repeats: int | None = None,
        baseline: SuiteResult | str | Path | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> SuiteResult:
        """Run the suite and wait for it. Inside an event loop, use `await suite.arun()`."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun(only, repeats, baseline, progress))
        raise RuntimeError("Suite.run() was called inside an event loop; use `await suite.arun()` instead")

    async def arun(
        self,
        only: Iterable[str] | None = None,
        repeats: int | None = None,
        baseline: SuiteResult | str | Path | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> SuiteResult:
        """Run every case `repeats` times. With a baseline, a case that looks worse than it gets more
        runs, up to max_repeats, so the comparison can tell a real drop from bad luck."""
        if isinstance(baseline, (str, Path)):
            baseline = SuiteResult.load(baseline)
        cases = self._select(only)
        gate = asyncio.Semaphore(self.concurrency)

        async def one(case: Case, attempt: int) -> RunResult:
            async with gate:
                traj = await self._run_agent(case.input)
            self._fill_cost(traj)
            # off the event loop: a judge check calls a model, and should not stall the other runs
            checks = [] if traj.error else await asyncio.to_thread(lambda: [check(traj) for check in case.expect])
            return RunResult(attempt, traj, checks)

        async def run_case(case: Case) -> CaseResult:
            n = repeats or case.repeats or self.repeats
            result = CaseResult(case.name, list(await asyncio.gather(*(one(case, i + 1) for i in range(n)))), case.must_pass, case.fingerprint)
            base = baseline.case(case.name) if isinstance(baseline, SuiteResult) else None
            if base is not None and result.n < self.max_repeats and _looks_worse(result, base):
                more = await asyncio.gather(*(one(case, i + 1) for i in range(result.n, self.max_repeats)))
                result.runs.extend(more)
            if progress:
                progress(f"{case.name}: {result.passes}/{result.n} passed")
            return result

        return SuiteResult(self.name, list(await asyncio.gather(*(run_case(c) for c in cases))))

    def _select(self, only: Iterable[str] | None) -> list[Case]:
        if not only:
            return list(self.cases)
        wanted = set(only)
        unknown = wanted - {c.name for c in self.cases}
        if unknown:
            raise ValueError(f"unknown case names: {sorted(unknown)}")
        return [c for c in self.cases if c.name in wanted]

    async def _run_agent(self, input: Any) -> Trajectory:
        from .integrations.auto import to_trajectory

        for attempt in range(self.retries + 1):
            recorded = Trajectory(input=input, source="recorded")
            start = time.perf_counter()
            task = asyncio.ensure_future(self._call(input, recorded))
            done, _ = await asyncio.wait({task}, timeout=self.timeout)
            if not done:
                task.cancel()  # a sync agent's thread cannot be stopped; it is abandoned and never blocks exit
                recorded.error = f"timed out after {self.timeout:g}s"
                traj = recorded
            else:
                try:
                    traj = to_trajectory(task.result(), input=input, recorded=recorded)
                except Exception as e:
                    if attempt < self.retries and _transient(e):
                        await asyncio.sleep(RETRY_DELAY_S * 2**attempt)
                        continue
                    traj = recorded
                    traj.error = f"{type(e).__name__}: {e}"
            if traj.latency_s is None:
                traj.latency_s = round(time.perf_counter() - start, 3)
            return traj
        raise AssertionError("unreachable")

    async def _call(self, input: Any, recorded: Trajectory) -> Any:
        _current.set(recorded)  # this runs in its own task, so the setting does not leak to other runs
        out = self.agent(input) if self._is_async else await _in_thread(functools.partial(self.agent, input))
        return await out if inspect.isawaitable(out) else out

    def _fill_cost(self, traj: Trajectory) -> None:
        if traj.cost_usd is None and self.price_per_mtok and traj.total_tokens:
            pin, pout = self.price_per_mtok
            traj.cost_usd = (traj.input_tokens * pin + traj.output_tokens * pout) / 1_000_000


def _looks_worse(result: CaseResult, base: CaseResult) -> bool:
    """Worth more runs: lower pass rate than the baseline, on the same case."""
    same_case = base.fingerprint is None or result.fingerprint is None or base.fingerprint == result.fingerprint
    return same_case and not result.must_pass and result.pass_rate < base.pass_rate


def _transient(error: BaseException) -> bool:
    """A rate limit, overload or network error from the model provider: try again, it says nothing about the agent."""
    e: BaseException | None = error
    for _ in range(5):  # frameworks often wrap the provider's error
        if e is None:
            return False
        status = getattr(e, "status_code", None) or getattr(e, "code", None)
        if type(e).__name__ in TRANSIENT_NAMES or (isinstance(status, int) and status in TRANSIENT_STATUS):
            return True
        e = e.__cause__ or e.__context__
    return False


def _in_thread(fn: Callable[[], Any]) -> asyncio.Future[Any]:
    """Run a sync agent in a daemon thread that sees the caller's context (so @tool calls are recorded).
    Daemon, so a run abandoned after a timeout cannot keep the process alive."""
    loop = asyncio.get_running_loop()
    future: asyncio.Future[Any] = loop.create_future()
    ctx = contextvars.copy_context()

    def settle(value: Any, error: BaseException | None) -> None:
        if not future.done():
            future.set_exception(error) if error is not None else future.set_result(value)

    def target() -> None:
        value, error = None, None
        try:
            value = ctx.run(fn)
        except Exception as e:
            error = e
        except BaseException as e:  # SystemExit and the like: report it as a failed run, do not kill the suite
            error = RuntimeError(f"agent raised {type(e).__name__}")
        try:
            loop.call_soon_threadsafe(settle, value, error)
        except RuntimeError:  # the event loop has closed: this run was abandoned after a timeout
            pass

    threading.Thread(target=target, name="agent-ratchet-run", daemon=True).start()
    return future
