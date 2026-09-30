from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Route(str, Enum):
    SELF = "self"
    SAFETY_MODEL = "safety_model"
    HUMAN = "human"


class Verdict(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class Action:
    """A tool call an agent wants to make, plus the risk metadata used to route it."""

    id: str
    tool: str
    description: str
    category: str
    reversibility: str
    blast_radius: str
    sensitivity: str
    params: dict[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()  # why the metadata looks the way it does (e.g. registry rules)


@dataclass(frozen=True)
class SafetyVerdict:
    verdict: Verdict
    confidence: float
    rationale: str
    model: str
    cost_usd: float = 0.0
    cached: bool = False
    error: str | None = None  # set when the verdict is a fail-closed fallback

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "model": self.model,
            "cost_usd": self.cost_usd,
            "cached": self.cached,
            "error": self.error,
        }


@dataclass(frozen=True)
class Decision:
    action_id: str
    route: Route
    tier: str
    score: int
    reasons: tuple[str, ...]
    timestamp: float
    deferred: bool = False  # needs a human but none reachable; action must wait
    degraded: bool = False  # wanted a human, fell back to the safety model
    budget_exempt: bool = False  # human interrupt that ignored the attention budget (critical)
    escalated: bool = False  # safety model asked for a human

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "route": self.route.value,
            "tier": self.tier,
            "score": self.score,
            "reasons": list(self.reasons),
            "timestamp": self.timestamp,
            "deferred": self.deferred,
            "degraded": self.degraded,
            "budget_exempt": self.budget_exempt,
            "escalated": self.escalated,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Decision:
        return cls(
            action_id=d["action_id"],
            route=Route(d["route"]),
            tier=d["tier"],
            score=d["score"],
            reasons=tuple(d["reasons"]),
            timestamp=d["timestamp"],
            deferred=d["deferred"],
            degraded=d["degraded"],
            budget_exempt=d.get("budget_exempt", False),
            escalated=d.get("escalated", False),
        )
