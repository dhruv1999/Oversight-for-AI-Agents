"""The simple way in: one object, one call before every tool call.

from oversight import Oversight

guard = Oversight()
check = guard.check("pay_invoice", {"vendor": "Acme", "amount": 420})
if check.allowed: run_it()
elif check.needs_person: ask_someone(check.explain())
"""

from __future__ import annotations

import functools
import inspect
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar, cast

from .allocator import Allocator
from .attention import AttentionTracker
from .gate import GateResult, Outcome, OversightGate, safe_review
from .log import DecisionLog
from .policies import DEFAULT_POLICY, DEFAULT_TOOLS
from .policy import Policy, Tier
from .registry import ToolRegistry
from .safety_model import HeuristicSafetyModel, SafetyModel
from .schema import Action, SafetyVerdict
from .store import FileStore, MemoryStore, StateStore

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True)
class Check:
    """The answer to 'may the agent do this?'."""

    action: Action
    result: GateResult

    @property
    def outcome(self) -> Outcome:
        return self.result.outcome

    @property
    def allowed(self) -> bool:
        return self.outcome == Outcome.EXECUTE

    @property
    def blocked(self) -> bool:
        return self.outcome == Outcome.BLOCK

    @property
    def needs_person(self) -> bool:
        return self.outcome == Outcome.ASK_HUMAN

    @property
    def waiting(self) -> bool:
        """A person must decide, but nobody can be asked right now. Queue it."""
        return self.outcome == Outcome.DEFER

    @property
    def risk(self) -> str:
        return self.result.decision.tier

    @property
    def reason(self) -> str:
        return self.result.reason

    @property
    def summary(self) -> str:
        """One plain sentence for people: what happens to this action and why."""
        d, v = self.result.decision, self.result.verdict
        if self.allowed:
            return "Low risk, so it runs without review." if v is None else "The automatic checker reviewed it and found nothing wrong."
        if self.blocked:
            why = v.rationale.removeprefix("heuristic: ") if v else self.reason
            return f"Stopped by the automatic checker: {why}."
        risk = "Critical" if d.budget_exempt else f"{self.risk.capitalize()} risk"
        if self.needs_person:
            if d.budget_exempt:
                return "Critical, so a person always decides."
            if d.escalated:
                return "The automatic checker was not sure, so a person decides."
            return f"{risk}, and the reviewer has attention left this hour."
        lead = "The automatic checker was not sure" if d.escalated and not d.degraded else risk
        if any("unavailable" in r for r in d.reasons):
            return f"{lead}, and the reviewer is away, so it waits for them."
        return f"{lead}, and the reviewer was asked recently, so it waits in their queue."

    def explain(self) -> str:
        head = f"{self.action.tool}: {self.outcome.value} ({self.risk} risk)"
        return "\n".join([head, *(f"  {r}" for r in self.result.decision.reasons)])


class _Answered:
    """A checker whose answer was already computed (outside the state lock)."""

    name = "precomputed"

    def __init__(self, verdict: SafetyVerdict):
        self.verdict = verdict

    def review(self, action: Action) -> SafetyVerdict:
        return self.verdict


class ActionBlocked(Exception):
    """Raised by a protected tool when the action must not run. `check` says why."""

    def __init__(self, check: Check):
        super().__init__(f"{check.action.tool} was not run: {check.reason}")
        self.check = check


class ActionDeferred(ActionBlocked):
    """Raised when a person must decide but nobody can be asked right now."""


class Oversight:
    """Default rules, a free rule based checker, and an interrupt budget from the policy file.

    Thread safe. Pass `state=".oversight"` (or any StateStore) to share one person's interrupt budget
    across processes; by default the budget lives in this process. Wall clock time is read here, at
    the edge; the routing core never reads a clock.
    """

    def __init__(
        self,
        policy: str | Path = DEFAULT_POLICY,
        tools: str | Path = DEFAULT_TOOLS,
        safety_model: SafetyModel | None = None,
        log_path: str | Path | None = None,
        clock: Callable[[], float] = time.time,
        state: str | Path | StateStore | None = None,
    ):
        self.policy = Policy.load(policy)
        self.registry = ToolRegistry.load(tools, self.policy)
        self.safety_model = safety_model or HeuristicSafetyModel()
        self.log = DecisionLog(log_path) if log_path else None
        self.store: StateStore = FileStore(state) if isinstance(state, (str, Path)) else (state or MemoryStore())
        self.rules_id = f"{self.policy.fingerprint}+{self.registry.fingerprint}"
        self._clock = clock

    def _tracker(self, state: dict[str, Any], now: float) -> AttentionTracker:
        att = AttentionTracker.from_config(self.policy.attention)
        att.restore(t for t in state["interrupt_times"] if now - t < att.window_seconds)
        att.set_available(state["available"])
        return att

    def _gate(self, state: dict[str, Any], now: float, checker: SafetyModel | None = None) -> tuple[OversightGate, AttentionTracker]:
        att = self._tracker(state, now)
        gate = OversightGate.from_policy(self.policy, Allocator(self.policy, att), checker or self.safety_model, self.log)
        gate.rules_id = self.rules_id
        return gate, att

    @classmethod
    def with_llm(
        cls,
        provider: str,
        model: str | None = None,
        max_spend_usd: float = 1.0,
        state_dir: str | Path = ".oversight",
        price_per_mtok: tuple[float, float] | None = None,
        client: Any = None,
        options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Oversight:
        """Use an AI model as the checker: provider "anthropic", "openai", "azure" or "gemini".

        Answers are cached in state_dir and spending stops at max_spend_usd. Only Claude prices are
        built in; for other models pass price_per_mtok=(input, output) in USD per million tokens.
        `options` go to the provider adapter (for example endpoint and api_version on Azure).
        """
        from .safety_model import build_llm_checker

        checker = build_llm_checker(provider, model, state_dir, max_spend_usd, price_per_mtok, client, **(options or {}))
        return cls(safety_model=checker, **kwargs)

    @classmethod
    def with_claude(
        cls,
        model: str = "claude-opus-5-5",
        max_spend_usd: float = 1.0,
        state_dir: str | Path = ".oversight",
        client: Any = None,
        **kwargs: Any,
    ) -> Oversight:
        """Use Claude as the checker. Answers are cached in state_dir; spending stops at max_spend_usd."""
        return cls.with_llm("anthropic", model, max_spend_usd, state_dir, client=client, **kwargs)

    def check(self, tool: str, params: dict[str, Any] | None = None, description: str = "", call_id: str | None = None, now: float | None = None) -> Check:
        """Decide who must approve this tool call. Records the interrupt if a person is asked."""
        action = self.registry.to_action(call_id or f"call-{uuid.uuid4().hex[:12]}", tool, dict(params or {}), description or f"call {tool}")
        # Medium risk actions always go to the checker, and the checker does not need the person's
        # state. Review them before taking the state lock, so a slow model never makes other agents wait.
        checker: SafetyModel | None = None
        if self.policy.assess(action).tier == Tier.MEDIUM:
            checker = _Answered(safe_review(self.safety_model, action))
        with self.store.transaction() as state:
            t = self._clock() if now is None else now
            gate, att = self._gate(state, t, checker)
            result = gate.review(action, t)
            state["interrupt_times"] = att.interrupt_times()
        return Check(action, result)

    def record_answer(self, check: Check, approved: bool, note: str = "", now: float | None = None) -> None:
        """Log what the person decided (for the audit trail)."""
        with self.store.transaction() as state:
            t = self._clock() if now is None else now
            gate, _ = self._gate(state, t)
            gate.record_human(check.action, approved, t, note, queued=check.waiting)

    def register_tool(
        self,
        name: str,
        category: str = "write",
        reversibility: str = "reversible",
        blast_radius: str = "project",
        sensitivity: str = "none",
    ) -> None:
        """Tell oversight how risky one of your own tools normally is. Unknown tools are treated as high risk.

        category: read, write, network, comms, exec, financial, admin
        reversibility: reversible, costly, irreversible
        blast_radius: self, project, org, external
        sensitivity: none, internal, pii, secret
        """
        self.registry.register(name, category, reversibility, blast_radius, sensitivity)

    def person_away(self) -> None:
        with self.store.transaction() as state:
            state["available"] = False

    def person_back(self) -> None:
        with self.store.transaction() as state:
            state["available"] = True

    def is_person_available(self) -> bool:
        with self.store.transaction() as state:
            return bool(state["available"])

    def attention(self, now: float | None = None) -> dict[str, Any]:
        """How much of the person's attention is left right now, for dashboards and the review page.

        next_ask_at is the earliest time a high risk action may interrupt them again (None if never).
        Critical actions ignore the budget and only need the person to be available.
        """
        with self.store.transaction() as state:
            t = self._clock() if now is None else now
            att = self._tracker(state, t)
            return {
                "now": t,
                "available": att.is_available(),
                "asked": att.interrupts_in_window(t),
                "limit": att.max_interrupts,
                "window_seconds": att.window_seconds,
                "next_ask_at": att.earliest_interrupt_time(t),
            }

    def protect(
        self,
        tool: str | None = None,
        ask: Callable[[Check], bool] | None = None,
    ) -> Callable[[F], F]:
        """Decorator that puts any Python tool function behind oversight.

            @guard.protect(ask=ask_on_slack)
            def pay_invoice(vendor: str, amount: float) -> str: ...

        Works with plain functions and coroutines, and keeps the signature, so agent frameworks
        (OpenAI Agents SDK, LangChain, and others) still build the right tool schema. The tool name
        defaults to the function name; params are the call's arguments by name. When a person is
        needed, `ask(check)` decides; without `ask` the call is refused. Refusals raise ActionBlocked
        (or ActionDeferred), whose message is written for the agent to read.
        """

        def decorate(fn: F) -> F:
            name = tool or fn.__name__
            sig = inspect.signature(fn)

            def gate(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Check:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                params = {k: v for k, v in bound.arguments.items() if k not in ("self", "cls")}
                check = self.check(name, params, description=(fn.__doc__ or "").strip().split("\n")[0])
                if check.allowed:
                    return check
                if check.needs_person and ask is not None:
                    approved = bool(ask(check))
                    self.record_answer(check, approved)
                    if approved:
                        return check
                if check.waiting:
                    raise ActionDeferred(check)
                raise ActionBlocked(check)

            if inspect.iscoroutinefunction(fn):

                @functools.wraps(fn)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    gate(args, kwargs)
                    return await fn(*args, **kwargs)

                return cast(F, async_wrapper)

            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                gate(args, kwargs)
                return fn(*args, **kwargs)

            return cast(F, wrapper)

        return decorate
