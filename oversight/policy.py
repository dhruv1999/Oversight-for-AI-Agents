from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
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
    safety_model: dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""  # sha256 of the policy file, so every logged decision names the rules that made it

    @classmethod
    def load(cls, path: str | Path) -> Policy:
        text = Path(path).read_text(encoding="utf-8")
        raw = yaml.safe_load(text)
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
        att = raw.get("attention") or {}
        missing = {"window_seconds", "max_interrupts_per_window", "min_gap_seconds"} - set(att)
        if missing:
            raise PolicyError(f"attention section missing {sorted(missing)}")
        for k in ("min_allow_confidence", "degraded_min_allow_confidence"):
            v = (raw.get("safety_model") or {}).get(k, 0.5)
            if not isinstance(v, (int, float)) or not 0 <= v <= 1:
                raise PolicyError(f"safety_model.{k} must be between 0 and 1")
        overrides = tuple(raw.get("overrides") or ())
        for o in overrides:
            cls._check_override(o, weights)
        return cls(
            int(raw["version"]),
            weights,
            tiers,
            overrides,
            dict(raw.get("attention") or {}),
            dict(raw.get("safety_model") or {}),
            hashlib.sha256(text.encode()).hexdigest()[:12],
        )

    @staticmethod
    def _check_override(o: Any, weights: dict[str, dict[str, int]]) -> None:
        if not isinstance(o, dict) or not {"name", "match", "tier", "reason"} <= set(o):
            raise PolicyError(f"override needs name, match, tier, reason: {o}")
        if str(o["tier"]).upper() not in Tier.__members__:
            raise PolicyError(f"override {o['name']}: unknown tier {o['tier']!r}")
        if not isinstance(o["match"], dict) or not o["match"]:
            raise PolicyError(f"override {o['name']}: match must be a non-empty mapping")
        for k, v in o["match"].items():
            if k not in DIMENSIONS or v not in weights[k]:
                raise PolicyError(f"override {o['name']}: bad match {k}={v!r}")

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
        reasons.extend(f"note: {n}" for n in action.notes)
        tier = max(t for t in Tier if score >= self.tiers[t])
        reasons.append(f"score {score} -> tier {tier}")
        for o in self.overrides:
            if all(getattr(action, k) == v for k, v in o["match"].items()):
                floor = Tier[o["tier"].upper()]
                if floor > tier:
                    tier = floor
                    reasons.append(f"override {o['name']}: {o['reason']} -> tier {tier}")
        return Assessment(score, tier, tuple(reasons))

    def weight(self, dim: str, value: str) -> int:
        try:
            return self.weights[dim][value]
        except KeyError as e:
            raise PolicyError(f"unknown {dim} value: {value!r}") from e
