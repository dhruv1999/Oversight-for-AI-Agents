from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Route(str, Enum):
    SELF = "self"
    SAFETY_MODEL = "safety_model"
    HUMAN = "human"


@dataclass(frozen=True)
class Action:
    id: str
    tool: str
    description: str
    category: str
    reversibility: str
    blast_radius: str
    sensitivity: str
    params: dict[str, Any] = field(default_factory=dict)


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
        )
