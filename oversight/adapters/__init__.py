"""Provider adapters. Only this package may import provider SDKs."""

from __future__ import annotations

from typing import Any

from .base import LLMClient

PROVIDERS = ("anthropic", "openai", "azure", "gemini")
DEFAULT_MODELS = {"anthropic": "claude-opus-5-5"}  # other providers: name the model (on Azure, the deployment)
EXTRAS = {"anthropic": "anthropic", "openai": "openai", "azure": "openai", "gemini": "gemini"}


def make_client(
    provider: str,
    model: str | None = None,
    json_schema: dict[str, Any] | None = None,
    price_per_mtok: tuple[float, float] | None = None,
    client: Any = None,
    **options: Any,
) -> LLMClient:
    """One model client for the checker. `options` are passed to the adapter (for example base_url,
    endpoint, api_version, effort, reasoning_effort or thinking_level)."""
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}; use one of {', '.join(PROVIDERS)}")
    model = model or DEFAULT_MODELS.get(provider)
    if not model:
        what = "an Azure deployment name" if provider == "azure" else "a model name"
        raise ValueError(f"the {provider} checker needs {what}: model=... in Python, --model on the command line")
    common: dict[str, Any] = {"model": model, "json_schema": json_schema, "price_per_mtok": price_per_mtok, "client": client, **options}
    try:
        return _construct(provider, common)
    except ImportError as e:
        raise ImportError(f'the {provider} checker needs its SDK: pip install "oversight-for-ai-agents[{EXTRAS[provider]}]"') from e


def _construct(provider: str, common: dict[str, Any]) -> LLMClient:
    if provider == "anthropic":
        from .anthropic_client import AnthropicClient

        return AnthropicClient(**common)
    if provider == "openai":
        from .openai_client import OpenAIClient

        return OpenAIClient(**common)
    if provider == "azure":
        from .openai_client import AzureOpenAIClient

        return AzureOpenAIClient(**common)
    from .gemini_client import GeminiClient

    return GeminiClient(**common)
