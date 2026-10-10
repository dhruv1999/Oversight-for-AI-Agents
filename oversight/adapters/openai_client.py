from __future__ import annotations

from typing import Any

from .base import LLMResponse


class OpenAIClient:
    """GPT models through the official OpenAI SDK, or any server that speaks the same API (base_url).

    - Uses Chat Completions, which OpenAI, Azure OpenAI and compatible servers all accept.
    - Optional structured output (`json_schema`, strict) guarantees parseable verdicts.
    - A refusal, or a reply stopped by a content filter, surfaces as stop_reason="refusal" and the
      safety model fails closed to ESCALATE.
    - Prices are not built in for these models; pass price_per_mtok so the spending cap can work.
    """

    provider = "openai"

    def __init__(
        self,
        model: str,
        max_tokens: int = 2048,
        reasoning_effort: str | None = "low",
        json_schema: dict[str, Any] | None = None,
        price_per_mtok: tuple[float, float] | None = None,
        base_url: str | None = None,
        client: Any = None,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort  # None for models without reasoning
        self.json_schema = json_schema
        self.price_per_mtok = price_per_mtok
        self.base_url = base_url
        if client is None:
            import openai

            client = openai.OpenAI(base_url=base_url) if base_url else openai.OpenAI()
        self._client = client

    @property
    def settings(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "max_tokens": self.max_tokens,
            "reasoning_effort": self.reasoning_effort,
            "json_schema": self.json_schema,
        }

    def complete(self, system: str, user: str) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_completion_tokens": self.max_tokens,
        }
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        if self.json_schema:
            kwargs["response_format"] = {"type": "json_schema", "json_schema": {"name": "verdict", "schema": self.json_schema, "strict": True}}
        r = self._client.chat.completions.create(**kwargs)
        choice = r.choices[0] if r.choices else None
        message = choice.message if choice is not None else None
        finish = choice.finish_reason if choice is not None else None
        stop: str | None
        if choice is None or getattr(message, "refusal", None) or finish == "content_filter":
            stop = "refusal"
        else:
            stop = "max_tokens" if finish == "length" else finish
        usage = r.usage
        if usage is None:  # bill the worst case rather than nothing
            tokens_in, tokens_out = (len(system) + len(user)) // 3, self.max_tokens
        else:
            tokens_in, tokens_out = usage.prompt_tokens, usage.completion_tokens
        return LLMResponse((message.content if message is not None else None) or "", tokens_in, tokens_out, r.model or self.model, stop)


class AzureOpenAIClient(OpenAIClient):
    """GPT models deployed on Azure OpenAI. `model` is your deployment name.

    The SDK reads AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY (or AZURE_OPENAI_AD_TOKEN) and
    OPENAI_API_VERSION when the matching argument is not given.
    """

    provider = "azure"

    def __init__(
        self,
        model: str,
        max_tokens: int = 2048,
        reasoning_effort: str | None = "low",
        json_schema: dict[str, Any] | None = None,
        price_per_mtok: tuple[float, float] | None = None,
        endpoint: str | None = None,
        api_version: str | None = None,
        client: Any = None,
    ):
        if client is None:
            import openai

            # values not given here come from the environment
            client = openai.AzureOpenAI(azure_endpoint=endpoint, api_version=api_version) if endpoint else openai.AzureOpenAI(api_version=api_version)
        super().__init__(model, max_tokens, reasoning_effort, json_schema, price_per_mtok, base_url=endpoint, client=client)
