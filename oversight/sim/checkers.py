"""Simulated automatic checkers with a chosen accuracy, for asking "how good must the checker be?"

A real checker (rules or a model) has some recall on harmful actions and some false alarm rate on
benign ones. SimulatedChecker has exactly the recall and false alarm rate you give it, decided per
unique action (so repeated actions get the same answer, like a cached model), and answers with
high confidence. It knows the hidden labels, so it only exists inside the simulation.
"""

from __future__ import annotations

import json

from ..human import stable_uniform
from ..schema import Action, SafetyVerdict, Verdict
from .scenarios import PoolItem


def content_key(tool: str, params: dict) -> str:
    return tool + json.dumps(params, sort_keys=True)


class SimulatedChecker:
    name = "simulated"

    def __init__(self, pool: list[PoolItem], recall: float, false_alarm: float = 0.02, confidence: float = 0.9, seed: int = 0):
        self.harmful = {content_key(p.tool, p.params): p.harmful for p in pool}
        self.recall = recall
        self.false_alarm = false_alarm
        self.confidence = confidence
        self.seed = seed

    def review(self, action: Action) -> SafetyVerdict:
        key = content_key(action.tool, action.params)
        u = stable_uniform("checker", self.seed, key)
        if self.harmful.get(key, False):
            caught = u < self.recall
        else:
            caught = u < self.false_alarm
        if caught:
            return SafetyVerdict(Verdict.BLOCK, self.confidence, "simulated checker: flagged", self.name)
        return SafetyVerdict(Verdict.ALLOW, self.confidence, "simulated checker: looks fine", self.name)
