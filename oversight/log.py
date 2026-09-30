from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import Decision


class DecisionLog:
    """Append-only JSONL audit log of every routing decision."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, d: Decision) -> None:
        self.write(d.to_dict())

    def write(self, record: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]

    def read(self) -> list[Decision]:
        return [Decision.from_dict(r) for r in self.records() if "route" in r]
