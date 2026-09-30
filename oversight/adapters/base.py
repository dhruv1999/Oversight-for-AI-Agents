from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    stop_reason: str | None = None


class LLMClient(Protocol):
    model: str
    max_tokens: int

    @property
    def settings(self) -> dict[str, Any]: ...  # everything besides the prompt that shapes the answer

    def complete(self, system: str, user: str) -> LLMResponse: ...


class ScriptedClient:
    """Deterministic stand-in for tests and dry runs: replays responses (or raises exceptions) in order."""

    def __init__(self, script: list[LLMResponse | Exception], model: str = "scripted", max_tokens: int = 512):
        self._script = list(script)
        self.model = model
        self.max_tokens = max_tokens
        self.calls = 0

    @property
    def settings(self) -> dict[str, Any]:
        return {"max_tokens": self.max_tokens}

    def complete(self, system: str, user: str) -> LLMResponse:
        self.calls += 1
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
