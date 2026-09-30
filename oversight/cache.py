from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def make_key(model: str, system: str, user: str, settings: dict[str, Any]) -> str:
    blob = json.dumps({"model": model, "system": system, "user": user, "settings": settings}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


class ResponseCache:
    """Model responses keyed by the exact request. JSONL on disk so a committed cache makes reruns free."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self._data: dict[str, dict[str, Any]] = {}
        if self.path and self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._data[row["key"]] = row["value"]

    def __len__(self) -> int:
        return len(self._data)

    def get(self, key: str) -> dict[str, Any] | None:
        return self._data.get(key)

    def put(self, key: str, value: dict[str, Any]) -> None:
        self._data[key] = value
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:
                f.write(json.dumps({"key": key, "value": value}, sort_keys=True) + "\n")
