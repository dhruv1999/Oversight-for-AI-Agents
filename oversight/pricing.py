"""USD per million tokens (input, output). Anthropic first-party list prices, cached 2026-09-25."""
from __future__ import annotations

import re

PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


class UnknownModelPricing(KeyError):
    pass


def normalise(model: str) -> str:
    return re.sub(r"-\d{8}$", "", model)


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    try:
        pin, pout = PRICES_PER_MTOK[normalise(model)]
    except KeyError as e:
        # fail closed: we refuse to spend on a model whose price we cannot bound
        raise UnknownModelPricing(model) from e
    return (input_tokens * pin + output_tokens * pout) / 1_000_000
