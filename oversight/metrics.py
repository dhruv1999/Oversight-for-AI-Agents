from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .schema import Decision, Route


def summarize(decisions: Iterable[Decision]) -> dict[str, Any]:
    ds = list(decisions)
    routes = {r.value: 0 for r in Route}
    tiers: dict[str, int] = {}
    for d in ds:
        routes[d.route.value] += 1
        tiers[d.tier] = tiers.get(d.tier, 0) + 1
    n = len(ds)
    return {
        "total": n,
        "routes": routes,
        "route_fractions": {k: (v / n if n else 0.0) for k, v in routes.items()},
        "tiers": tiers,
        "degraded": sum(d.degraded for d in ds),
        "deferred": sum(d.deferred for d in ds),
        "human_interrupts": sum(d.route == Route.HUMAN and not d.deferred for d in ds),
    }
