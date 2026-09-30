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
from .redact import redact, redact_text
from .safety_model import SafetyModel
from .schema import Action, Decision, Route, SafetyVerdict, Verdict


class Router(Protocol):
    name: str

    def decide(self, action: Action, now: float) -> Decision: ...

    def escalate(self, decision: Decision, now: float, why: str) -> Decision: ...


LOG_VERSION = 1


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
        takeover: str = "veto",
    ):
        self.router = router
        self.safety_model = safety_model
        self.min_allow_confidence = min_allow_confidence
        self.degraded_min_allow_confidence = degraded_min_allow_confidence
        self.log = log
        self.takeover = takeover  # "veto": when taking over from a busy person, the checker may block but never approve
        self.rules_id = ""  # fingerprint of the policy (and tool registry) that made the decisions

    @classmethod
    def from_policy(cls, policy: Policy, router: Router, safety_model: SafetyModel | None, log: DecisionLog | None = None) -> OversightGate:
        cfg = policy.safety_model
        gate = cls(
            router,
            safety_model,
            cfg.get("min_allow_confidence", 0.6),
            cfg.get("degraded_min_allow_confidence", 0.85),
            log,
            cfg.get("takeover", "veto"),
        )
        gate.rules_id = policy.fingerprint
        return gate

    def review(self, action: Action, now: float) -> GateResult:
        d = self.router.decide(action, now)
        verdict = None
        if d.route == Route.SELF:
            res = GateResult(Outcome.EXECUTE, d, None, "no review needed")
        elif d.route == Route.HUMAN:
            res = GateResult(Outcome.DEFER if d.deferred else Outcome.ASK_HUMAN, d, None, d.reasons[-1])
        else:
            verdict = self._safe_review(action)
            bar = self.degraded_min_allow_confidence if d.degraded else self.min_allow_confidence
            if verdict.verdict == Verdict.BLOCK:
                res = GateResult(Outcome.BLOCK, d, verdict, f"safety model blocked: {verdict.rationale}")
            elif d.degraded and self.takeover == "veto" and verdict.verdict == Verdict.ALLOW:
                d = self.router.escalate(d, now, "checker found nothing, but it may not approve high risk actions on its own")
                res = GateResult(Outcome.DEFER if d.deferred else Outcome.ASK_HUMAN, d, verdict, d.reasons[-1])
            elif verdict.verdict == Verdict.ALLOW and verdict.confidence >= bar:
                res = GateResult(Outcome.EXECUTE, d, verdict, f"safety model allowed ({verdict.confidence:.2f} >= {bar})")
            else:
                why = verdict.rationale if verdict.verdict == Verdict.ESCALATE else f"allow confidence {verdict.confidence:.2f} below {bar}"
                d = self.router.escalate(d, now, why)
                res = GateResult(Outcome.DEFER if d.deferred else Outcome.ASK_HUMAN, d, verdict, d.reasons[-1])
        self._log("gate", action, res)
        return res

    def _safe_review(self, action: Action) -> SafetyVerdict:
        """Fail closed: a missing, crashing or over budget safety model means 'ask a human', never 'allow'."""
        if self.safety_model is None:
            return SafetyVerdict(Verdict.ESCALATE, 0.0, "no safety model configured", "none", error="no_safety_model")
        try:
            return self.safety_model.review(action)
        except Exception as e:  # includes SpendLimitExceeded
            name = getattr(self.safety_model, "name", "safety_model")
            return SafetyVerdict(Verdict.ESCALATE, 0.0, f"safety model unavailable: {type(e).__name__}", name, error=f"{type(e).__name__}: {e}")

    def record_human(self, action: Action, approved: bool, now: float, rationale: str = "", queued: bool = False) -> None:
        if self.log:
            self.log.write(
                {
                    "log_version": LOG_VERSION,
                    "rules": self.rules_id,
                    "event": "human",
                    "action_id": action.id,
                    "approved": approved,
                    "timestamp": now,
                    "rationale": rationale,
                    "queued": queued,
                }
            )

    def _log(self, event: str, action: Action, res: GateResult) -> None:
        if not self.log:
            return
        act = asdict(action)
        act["params"] = redact(act["params"])
        act["description"] = redact_text(act["description"])
        rec: dict[str, Any] = {
            "log_version": LOG_VERSION,
            "rules": self.rules_id,
            "event": event,
            "router": self.router.name,
            "action": act,
            "outcome": res.outcome.value,
            "reason": res.reason,
        }
        rec.update(res.decision.to_dict())
        rec["verdict"] = res.verdict.to_dict() if res.verdict else None
        self.log.write(rec)
