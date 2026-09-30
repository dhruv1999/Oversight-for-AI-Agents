"""The simple way in: one object, one call before every tool call.

from oversight import Oversight

guard = Oversight()
check = guard.check("pay_invoice", {"vendor": "Acme", "amount": 420})
if check.allowed: run_it()
elif check.needs_person: ask_someone(check.explain())
"""

from __future__ import annotations

import itertools
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .allocator import Allocator
from .attention import AttentionTracker
from .gate import GateResult, Outcome, OversightGate
from .log import DecisionLog
from .policies import DEFAULT_POLICY, DEFAULT_TOOLS
from .policy import Policy
from .registry import ToolRegistry
from .safety_model import HeuristicSafetyModel, SafetyModel
from .schema import Action


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

    def explain(self) -> str:
        head = f"{self.action.tool}: {self.outcome.value} ({self.risk} risk)"
        return "\n".join([head, *(f"  {r}" for r in self.result.decision.reasons)])


class Oversight:
    """Default rules, a free rule based checker, and an interrupt budget from the policy file.

    Thread safe. Wall clock time is read here, at the edge; the routing core never reads a clock.
    """

    def __init__(
        self,
        policy: str | Path = DEFAULT_POLICY,
        tools: str | Path = DEFAULT_TOOLS,
        safety_model: SafetyModel | None = None,
        log_path: str | Path | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.policy = Policy.load(policy)
        self.registry = ToolRegistry.load(tools, self.policy)
        self.attention = AttentionTracker.from_config(self.policy.attention)
        self.gate = OversightGate.from_policy(
            self.policy, Allocator(self.policy, self.attention), safety_model or HeuristicSafetyModel(), DecisionLog(log_path) if log_path else None
        )
        self._clock = clock
        self._lock = threading.Lock()
        self._ids = itertools.count(1)

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
        from .adapters.anthropic_client import AnthropicClient
        from .cache import ResponseCache
        from .safety_model import VERDICT_SCHEMA, LLMSafetyModel
        from .spend import SpendTracker

        d = Path(state_dir)
        checker = LLMSafetyModel(
            AnthropicClient(model=model, json_schema=VERDICT_SCHEMA, client=client),
            cache=ResponseCache(d / "review_cache.jsonl"),
            spend=SpendTracker(max_spend_usd, ledger_path=d / "spend_ledger.jsonl"),
        )
        return cls(safety_model=checker, **kwargs)

    def check(self, tool: str, params: dict[str, Any] | None = None, description: str = "", call_id: str | None = None, now: float | None = None) -> Check:
        with self._lock:
            action = self.registry.to_action(call_id or f"call-{next(self._ids)}", tool, dict(params or {}), description or f"call {tool}")
            return Check(action, self.gate.review(action, self._clock() if now is None else now))

    def record_answer(self, check: Check, approved: bool, note: str = "", now: float | None = None) -> None:
        """Log what the person decided (for the audit trail)."""
        with self._lock:
            self.gate.record_human(check.action, approved, self._clock() if now is None else now, note, queued=check.waiting)

    def person_away(self) -> None:
        with self._lock:
            self.attention.set_available(False)

    def person_back(self) -> None:
        with self._lock:
            self.attention.set_available(True)
