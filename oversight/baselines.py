"""Comparison routers. Same interface as Allocator: decide() and escalate(). Deterministic, no models."""

from __future__ import annotations

from dataclasses import replace

from .attention import AttentionTracker
from .policy import Policy, Tier
from .schema import Action, Decision, Route


class _Router:
    name = "base"

    def __init__(self, policy: Policy, attention: AttentionTracker):
        self.policy = policy
        self.attention = attention

    def _make(self, action: Action, now: float, route: Route, reason: str) -> Decision:
        a = self.policy.assess(action)
        reasons = a.reasons + (f"{self.name}: {reason}",)
        deferred = False
        if route == Route.HUMAN:
            if self.attention.is_available():
                self.attention.record_interrupt(now)
            else:
                deferred = True
                reasons += ("human unavailable; deferred",)
        return Decision(action.id, route, str(a.tier), a.score, reasons, now, deferred)

    def escalate(self, decision: Decision, now: float, why: str) -> Decision:
        reasons = decision.reasons + (f"safety model escalated: {why}",)
        if self.attention.can_interrupt(now)[0]:
            self.attention.record_interrupt(now)
            return replace(decision, route=Route.HUMAN, escalated=True, reasons=reasons)
        return replace(decision, route=Route.HUMAN, escalated=True, deferred=True, reasons=reasons + ("deferred",))


class NoOversight(_Router):
    name = "no_oversight"

    def decide(self, action: Action, now: float) -> Decision:
        return self._make(action, now, Route.SELF, "every action runs unreviewed")


class AlwaysModel(_Router):
    name = "always_model"

    def decide(self, action: Action, now: float) -> Decision:
        return self._make(action, now, Route.SAFETY_MODEL, "safety model reviews every action")


class AlwaysHuman(_Router):
    name = "always_human"

    def decide(self, action: Action, now: float) -> Decision:
        return self._make(action, now, Route.HUMAN, "human reviews every action")


class StaticRisk(_Router):
    """Risk tiers only: ignores the attention budget and never degrades."""

    name = "static_risk"

    def decide(self, action: Action, now: float) -> Decision:
        tier = self.policy.assess(action).tier
        if tier == Tier.LOW:
            return self._make(action, now, Route.SELF, "low risk")
        if tier == Tier.MEDIUM:
            return self._make(action, now, Route.SAFETY_MODEL, "medium risk")
        return self._make(action, now, Route.HUMAN, f"{tier} risk")
