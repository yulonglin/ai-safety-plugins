"""Provider registry: ``provider`` string -> a `JudgeClient`."""

from __future__ import annotations

from transcript_judge.providers.base import (
    SUPPORTED_PARAMS,
    JudgeClient,
    MissingAPIKeyError,
    ProviderSettings,
    UnsupportedParamError,
    resolve_key,
    strict_grammar,
    validate_params,
)

PROVIDERS = ("anthropic", "openai", "openrouter")


def get_client(provider: str, **kwargs) -> JudgeClient:
    if provider == "anthropic":
        from transcript_judge.providers.anthropic import AnthropicClient

        return AnthropicClient(**kwargs)
    if provider == "openai":
        from transcript_judge.providers.openai import OpenAIClient

        return OpenAIClient(**kwargs)
    if provider == "openrouter":
        from transcript_judge.providers.openrouter import OpenRouterClient

        return OpenRouterClient(**kwargs)
    raise ValueError(f"unknown provider {provider!r}; expected one of {', '.join(PROVIDERS)}")


__all__ = [
    "PROVIDERS",
    "SUPPORTED_PARAMS",
    "JudgeClient",
    "MissingAPIKeyError",
    "ProviderSettings",
    "UnsupportedParamError",
    "get_client",
    "resolve_key",
    "strict_grammar",
    "validate_params",
]
