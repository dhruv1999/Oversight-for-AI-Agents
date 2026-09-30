"""A workday of agent actions sampled from the pool."""
from __future__ import annotations

import random
from dataclasses import dataclass

from .scenarios import PoolItem, template_weights


@dataclass(frozen=True)
class Event:
    t: float
    item: PoolItem


def sample_episode(
    pool: list[PoolItem],
    rng: random.Random,
    day_seconds: int = 8 * 3600,
    mean_gap_seconds: float = 300.0,
    harmful_rate: float = 0.08,
) -> list[Event]:
    """Poisson arrivals over the day. Benign actions follow template weights; harmful ones are uniform over templates."""
    weights = template_weights()
    by_template: dict[str, list[PoolItem]] = {}
    for p in pool:
        by_template.setdefault(p.template, []).append(p)
    benign_t = sorted(t for t, items in by_template.items() if not items[0].harmful)
    harmful_t = sorted(t for t, items in by_template.items() if items[0].harmful)
    events: list[Event] = []
    t = rng.expovariate(1 / mean_gap_seconds)
    while t < day_seconds:
        if harmful_t and rng.random() < harmful_rate:
            tid = rng.choice(harmful_t)
        else:
            tid = rng.choices(benign_t, weights=[weights[x] for x in benign_t])[0]
        events.append(Event(round(t, 1), rng.choice(by_template[tid])))
        t += rng.expovariate(1 / mean_gap_seconds)
    return events
