from __future__ import annotations

from typing import Any

from .base import LLMResponse

# Finish and block reasons that mean the model declined to answer.
_REFUSALS = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "JAILBREAK", "MODEL_ARMOR", "OTHER"}


def _without_additional_properties(schema: Any) -> Any:
    """Gemini's schema support is a subset of JSON Schema; the verdict is validated after parsing anyway."""
    if isinstance(schema, dict):
        return {k: _without_additional_properties(v) for k, v in schema.items() if k != "additionalProperties"}
    if isinstance(schema, list):
        return [_without_additional_properties(v) for v in schema]
    return schema


class GeminiClient:
    """Gemini models through Google's official google-genai SDK.

    - The SDK reads GEMINI_API_KEY (or GOOGLE_API_KEY); for Vertex AI pass your own genai.Client.
    - Optional structured output (`json_schema`) asks for JSON that matches the verdict schema.
    - A blocked prompt or a reply stopped for safety surfaces as stop_reason="refusal" and the
      safety model fails closed to ESCALATE.
    - Thinking tokens are billed as output, so they are counted as output here.
    - Prices are not built in for these models; pass price_per_mtok so the spending cap can work.
    """

    provider = "gemini"

    def __init__(
        self,
        model: str,
        max_tokens: int = 2048,
        thinking_level: str | None = "low",
        json_schema: dict[str, Any] | None = None,
        price_per_mtok: tuple[float, float] | None = None,
        client: Any = None,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.thinking_level = thinking_level  # None for models that do not take a thinking level
        self.json_schema = json_schema
        self.price_per_mtok = price_per_mtok
        if client is None:
            from google import genai

            client = genai.Client()
        self._client = client

    @property
    def settings(self) -> dict[str, Any]:
        return {"provider": self.provider, "max_tokens": self.max_tokens, "thinking_level": self.thinking_level, "json_schema": self.json_schema}

    def complete(self, system: str, user: str) -> LLMResponse:
        from google.genai import types

        config: dict[str, Any] = {"system_instruction": system, "max_output_tokens": self.max_tokens}
        if self.thinking_level:
            config["thinking_config"] = types.ThinkingConfig(thinking_level=types.ThinkingLevel(self.thinking_level.upper()))
        if self.json_schema:
            config["response_mime_type"] = "application/json"
            config["response_json_schema"] = _without_additional_properties(self.json_schema)
        r = self._client.models.generate_content(model=self.model, contents=user, config=types.GenerateContentConfig(**config))

        candidates = r.candidates or []
        first = candidates[0] if candidates else None
        finish = getattr(first.finish_reason, "name", None) if first is not None and first.finish_reason else None
        blocked = getattr(getattr(r, "prompt_feedback", None), "block_reason", None)
        if first is None or blocked or finish in _REFUSALS:
            stop = "refusal"
        else:
            stop = "max_tokens" if finish == "MAX_TOKENS" else (finish or "stop").lower()
        parts = (first.content.parts or []) if first is not None and first.content else []
        text = "".join(p.text for p in parts if p.text and not p.thought)
        usage = r.usage_metadata
        if usage is None:  # bill the worst case rather than nothing
            tokens_in, tokens_out = (len(system) + len(user)) // 3, self.max_tokens
        else:
            tokens_in = usage.prompt_token_count or 0
            tokens_out = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
        return LLMResponse(text, tokens_in, tokens_out, r.model_version or self.model, stop)
