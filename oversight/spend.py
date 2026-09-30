from __future__ import annotations

import json
import os
from pathlib import Path

from .pricing import cost_usd


class SpendLimitExceeded(RuntimeError):
    pass


class SpendTracker:
    """Hard USD cap on model spend. Checked with a worst-case estimate *before* every call."""

    def __init__(self, max_usd: float, ledger_path: str | Path | None = None):
        self.max_usd = max_usd
        self.ledger_path = Path(ledger_path) if ledger_path else None
        self.spent_usd = 0.0
        if self.ledger_path and self.ledger_path.exists():
            for line in self.ledger_path.read_text().splitlines():
                if line.strip():
                    self.spent_usd += json.loads(line)["cost_usd"]

    @classmethod
    def from_env(cls, default: float = 1.0, ledger_path: str | Path | None = None) -> SpendTracker:
        return cls(float(os.environ.get("MAX_SPEND_USD", default)), ledger_path)

    @property
    def remaining_usd(self) -> float:
        return self.max_usd - self.spent_usd

    def check(self, model: str, est_input_tokens: int, max_output_tokens: int) -> None:
        worst = cost_usd(model, est_input_tokens, max_output_tokens)
        if self.spent_usd + worst > self.max_usd:
            raise SpendLimitExceeded(f"next call could cost ${worst:.4f}; spent ${self.spent_usd:.4f} of MAX_SPEND_USD=${self.max_usd:.2f}")

    def record(self, model: str, input_tokens: int, output_tokens: int) -> float:
        c = cost_usd(model, input_tokens, output_tokens)
        self.spent_usd += c
        if self.ledger_path:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with self.ledger_path.open("a") as f:
                f.write(json.dumps({"model": model, "input_tokens": input_tokens, "output_tokens": output_tokens, "cost_usd": c}) + "\n")
        return c
