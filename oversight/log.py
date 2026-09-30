from __future__ import annotations

import json
from pathlib import Path

from .schema import Decision


class DecisionLog:
    """Append-only JSONL audit log of every routing decision."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, d: Decision) -> None:
        with self.path.open("a") as f:
            f.write(json.dumps(d.to_dict()) + "\n")

    def read(self) -> list[Decision]:
        if not self.path.exists():
            return []
        return [Decision.from_dict(json.loads(l)) for l in self.path.read_text().splitlines() if l]
