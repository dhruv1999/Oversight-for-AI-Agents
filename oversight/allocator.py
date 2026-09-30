from __future__ import annotations

from .attention import AttentionTracker
from .policy import Policy, Tier
from .schema import Action, Decision, Route


class Allocator:
    """Deterministic router: risk tier + human attention -> route. Never calls a model."""

    def __init__(self, policy: Policy, attention: AttentionTracker):
        self.policy = policy
        self.attention = attention

    def decide(self, action: Action, now: float) -> Decision:
        a = self.policy.assess(action)
        reasons = list(a.reasons)
        route, deferred, degraded = Route.SELF, False, False

        if a.tier == Tier.LOW:
            reasons.append("low risk: agent proceeds on its own")
        elif a.tier == Tier.MEDIUM:
            route = Route.SAFETY_MODEL
            reasons.append("medium risk: safety model reviews")
        elif a.tier == Tier.HIGH:
            ok, why = self.attention.can_interrupt(now)
            if ok:
                route = Route.HUMAN
                reasons.append(f"high risk: escalate to human ({why})")
            else:
                route, degraded = Route.SAFETY_MODEL, True
                reasons.append(f"high risk: human not reachable ({why}); degraded to safety model")
        else:  # CRITICAL: a human is mandatory, budget is bypassed, never a model fallback
            route = Route.HUMAN
            if self.attention.is_available():
                reasons.append("critical risk: human required (budget bypassed)")
            else:
                deferred = True
                reasons.append("critical risk: human required but unavailable; action deferred")

        if route == Route.HUMAN and not deferred:
            self.attention.record_interrupt(now)
        return Decision(action.id, route, str(a.tier), a.score, tuple(reasons), now, deferred, degraded)
