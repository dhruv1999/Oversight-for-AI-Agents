from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any

import yaml

from .schema import Action

DIMENSIONS = ("category", "reversibility", "blast_radius", "sensitivity")


class PolicyError(ValueError):
    pass


class Tier(IntEnum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3

    def __str__(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class Assessment:
    score: int
    tier: Tier
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Policy:
    version: int
    weights: dict[str, dict[str, int]]
    tiers: dict[Tier, int]
    overrides: tuple[dict[str, Any], ...]
    attention: dict[str, int]

    @classmethod
    def load(cls, path: str | Path) -> Policy:
        raw = yaml.safe_load(Path(path).read_text())
        try:
            weights = raw["weights"]
            for dim in DIMENSIONS:
                if not weights.get(dim):
                    raise PolicyError(f"weights.{dim} missing or empty")
            tiers = {Tier[k.upper()]: int(v) for k, v in raw["tiers"].items()}
        except (KeyError, AttributeError, TypeError) as e:
            raise PolicyError(f"malformed policy: {e!r}") from e
        if set(tiers) != set(Tier):
            raise PolicyError("tiers must define low, medium, high, critical")
        mins = [tiers[t] for t in sorted(Tier)]
        if mins != sorted(set(mins)):
            raise PolicyError("tier thresholds must be strictly increasing")
        overrides = tuple(raw.get("overrides") or ())
        for o in overrides:
            if Tier[o["tier"].upper()] is None or not o.get("match"):
                raise PolicyError(f"bad override: {o}")
        return cls(int(raw["version"]), weights, tiers, overrides, dict(raw.get("attention") or {}))

    def assess(self, action: Action) -> Assessment:
        score = 0
        reasons = []
        for dim in DIMENSIONS:
            value = getattr(action, dim)
            table = self.weights[dim]
            if value not in table:
                raise PolicyError(f"unknown {dim} value: {value!r}")
            score += table[value]
            reasons.append(f"{dim}={value} (+{table[value]})")
        tier = max(t for t in Tier if score >= self.tiers[t])
        reasons.append(f"score {score} -> tier {tier}")
        for o in self.overrides:
            if all(getattr(action, k, None) == v for k, v in o["match"].items()):
                floor = Tier[o["tier"].upper()]
                if floor > tier:
                    tier = floor
                    reasons.append(f"override {o['name']}: {o['reason']} -> tier {tier}")
        return Assessment(score, tier, tuple(reasons))
