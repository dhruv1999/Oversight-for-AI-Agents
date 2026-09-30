"""The runtime an agent calls before every tool call.

route (deterministic) -> optional safety-model review -> EXECUTE / BLOCK / ASK_HUMAN / DEFER.
The gate never talks to the human itself; the caller owns that channel (console, chat
approval, Claude Code permission prompt, or a simulated human) and reports back via
record_human(). Every step is written to the audit log.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Protocol

from .log import DecisionLog
from .policy import Policy
from .safety_model import SafetyModel
from .schema import Action, Decision, Route, SafetyVerdict, Verdict


class Router(Protocol):
    name: str

    def decide(self, action: Action, now: float) -> Decision: ...

    def escalate(self, decision: Decision, now: float, why: str) -> Decision: ...


class Outcome(str, Enum):
    EXECUTE = "execute"
    BLOCK = "block"
    ASK_HUMAN = "ask_human"
    DEFER = "defer"


@dataclass(frozen=True)
class GateResult:
    outcome: Outcome
    decision: Decision
    verdict: SafetyVerdict | None
    reason: str


class OversightGate:
    def __init__(
        self,
        router: Router,
        safety_model: SafetyModel | None,
        min_allow_confidence: float = 0.6,
        degraded_min_allow_confidence: float = 0.85,
        log: DecisionLog | None = None,
    ):
        self.router = router
        self.safety_model = safety_model
        self.min_allow_confidence = min_allow_confidence
        self.degraded_min_allow_confidence = degraded_min_allow_confidence
        self.log = log

    @classmethod
    def from_policy(cls, policy: Policy, router: Router, safety_model: SafetyModel | None, log: DecisionLog | None = None) -> OversightGate:
        cfg = policy.safety_model
        return cls(router, safety_model, cfg.get("min_allow_confidence", 0.6), cfg.get("degraded_min_allow_confidence", 0.85), log)

    def review(self, action: Action, now: float) -> GateResult:
        d = self.router.decide(action, now)
        verdict = None
        if d.route == Route.SELF:
            res = GateResult(Outcome.EXECUTE, d, None, "no review needed")
        elif d.route == Route.HUMAN:
            res = GateResult(Outcome.DEFER if d.deferred else Outcome.ASK_HUMAN, d, None, d.reasons[-1])
        else:
            if self.safety_model is None:
                raise RuntimeError("route is safety_model but no safety model is configured")
            verdict = self.safety_model.review(action)
            bar = self.degraded_min_allow_confidence if d.degraded else self.min_allow_confidence
            if verdict.verdict == Verdict.BLOCK:
                res = GateResult(Outcome.BLOCK, d, verdict, f"safety model blocked: {verdict.rationale}")
            elif verdict.verdict == Verdict.ALLOW and verdict.confidence >= bar:
                res = GateResult(Outcome.EXECUTE, d, verdict, f"safety model allowed ({verdict.confidence:.2f} >= {bar})")
            else:
                why = verdict.rationale if verdict.verdict == Verdict.ESCALATE else f"allow confidence {verdict.confidence:.2f} below {bar}"
                d = self.router.escalate(d, now, why)
                res = GateResult(Outcome.DEFER if d.deferred else Outcome.ASK_HUMAN, d, verdict, d.reasons[-1])
        self._log("gate", action, res)
        return res

    def record_human(self, action: Action, approved: bool, now: float, rationale: str = "", queued: bool = False) -> None:
        if self.log:
            self.log.write({"event": "human", "action_id": action.id, "approved": approved, "timestamp": now, "rationale": rationale, "queued": queued})

    def _log(self, event: str, action: Action, res: GateResult) -> None:
        if not self.log:
            return
        rec: dict[str, Any] = {"event": event, "router": self.router.name, "action": asdict(action), "outcome": res.outcome.value, "reason": res.reason}
        rec.update(res.decision.to_dict())
        rec["verdict"] = res.verdict.to_dict() if res.verdict else None
        self.log.write(rec)
