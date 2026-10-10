from __future__ import annotations

from typing import Any

from .base import LLMResponse

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicClient:
    """Claude via the official Anthropic SDK.

    - Thinking is left at the model default (always on for Claude Opus 5.5); `effort` controls depth.
    - Optional structured output (`json_schema`) guarantees parseable verdicts.
    - Server-side refusal fallbacks are on by default; a refusal that survives them surfaces as
      stop_reason="refusal" and the safety model fails closed to ESCALATE.
    """

    def __init__(
        self,
        model: str = "claude-opus-5-5",
        max_tokens: int = 2048,
        effort: str = "low",
        json_schema: dict[str, Any] | None = None,
        fallbacks: bool = True,
        price_per_mtok: tuple[float, float] | None = None,
        client: Any = None,
    ):
        self.model = model
        self.price_per_mtok = price_per_mtok
        self.max_tokens = max_tokens
        self.effort = effort
        self.json_schema = json_schema
        self.fallbacks = fallbacks
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client = client

    @property
    def settings(self) -> dict[str, Any]:
        return {"max_tokens": self.max_tokens, "effort": self.effort, "json_schema": self.json_schema, "fallbacks": self.fallbacks}

    def complete(self, system: str, user: str) -> LLMResponse:
        output_config: dict[str, Any] = {"effort": self.effort}
        if self.json_schema:
            output_config["format"] = {"type": "json_schema", "schema": self.json_schema}
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": output_config,
        }
        if self.fallbacks:
            kwargs["betas"] = [FALLBACK_BETA]
            kwargs["fallbacks"] = "default"
        r = self._client.beta.messages.create(**kwargs)
        text = "".join(b.text for b in r.content if getattr(b, "type", None) == "text")
        return LLMResponse(text, r.usage.input_tokens, r.usage.output_tokens, r.model, r.stop_reason)
