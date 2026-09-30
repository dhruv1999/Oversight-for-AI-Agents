from __future__ import annotations

from dataclasses import replace

from .attention import AttentionTracker
from .policy import Policy, Tier
from .schema import Action, Decision, Route


class Allocator:
    """Deterministic router: risk tier + human attention -> route. Never calls a model."""

    name = "adaptive"

    def __init__(self, policy: Policy, attention: AttentionTracker, fallback_to_checker: bool = True, pacing: bool = False):
        self.policy = policy
        self.attention = attention
        # pacing: as the budget fills up, keep the remaining interrupts for the riskiest high actions
        self.pacing = pacing
        # False = ablation: over budget high risk actions wait for the person instead of going to the checker
        self.fallback_to_checker = fallback_to_checker

    def decide(self, action: Action, now: float) -> Decision:
        a = self.policy.assess(action)
        reasons = list(a.reasons)
        route, deferred, degraded, exempt = Route.SELF, False, False, False

        if a.tier == Tier.LOW:
            reasons.append("low risk: agent proceeds on its own")
        elif a.tier == Tier.MEDIUM:
            route = Route.SAFETY_MODEL
            reasons.append("medium risk: safety model reviews")
        elif a.tier == Tier.HIGH:
            ok, why = self.attention.can_interrupt(now)
            if ok and self.pacing:
                bar = self._pacing_bar(now)
                if a.score < bar:
                    used = f"{self.attention.interrupts_in_window(now)}/{self.attention.max_interrupts}"
                    ok, why = False, f"pacing: score {a.score} below {bar:.1f} with {used} of the budget used"
            if ok:
                route = Route.HUMAN
                reasons.append(f"high risk: escalate to human ({why})")
            elif self.fallback_to_checker:
                route, degraded = Route.SAFETY_MODEL, True
                reasons.append(f"high risk: human not reachable ({why}); degraded to safety model")
            else:
                route, deferred = Route.HUMAN, True
                reasons.append(f"high risk: human not reachable ({why}); waits for the human")
        else:  # CRITICAL: a human is mandatory, budget is bypassed, never a model fallback
            route, exempt = Route.HUMAN, True
            if self.attention.is_available():
                reasons.append("critical risk: human required (budget bypassed)")
            else:
                deferred = True
                reasons.append("critical risk: human required but unavailable; action deferred")

        if route == Route.HUMAN and not deferred:
            self.attention.record_interrupt(now)
        return Decision(action.id, route, str(a.tier), a.score, tuple(reasons), now, deferred, degraded, exempt)

    def _pacing_bar(self, now: float) -> float:
        """Minimum score for a high risk interrupt: the bottom of the high tier when the budget is empty,
        rising linearly towards the critical tier as it fills."""
        lo, hi = self.policy.tiers[Tier.HIGH], self.policy.tiers[Tier.CRITICAL]
        used = self.attention.interrupts_in_window(now) / max(1, self.attention.max_interrupts)
        return lo + (hi - lo) * used

    def escalate(self, decision: Decision, now: float, why: str) -> Decision:
        """The safety model asked for a human. Interrupt within budget, otherwise defer (never auto-allow)."""
        ok, reach = self.attention.can_interrupt(now)
        reasons = decision.reasons + (f"safety model escalated: {why}",)
        if ok:
            self.attention.record_interrupt(now)
            return replace(decision, route=Route.HUMAN, escalated=True, reasons=reasons + (f"human reviews ({reach})",))
        return replace(decision, route=Route.HUMAN, escalated=True, deferred=True, reasons=reasons + (f"human not reachable ({reach}); deferred",))
