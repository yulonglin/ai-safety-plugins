"""The provider contract, plus the single JSON grammar every provider enforces.

Three thin `httpx` wrappers rather than three vendor SDKs: the surface we need
is one POST, and depending on three SDK release cadences to send the same JSON
buys nothing.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from transcript_judge.models import JudgeResponse, RawCompletion

#: Name of the forced tool on Anthropic, and of the json_schema elsewhere.
GRAMMAR_NAME = "emit_judgement"

DEFAULT_TIMEOUT_SECONDS = 120.0

#: Enough of an error body to carry the provider's reason, not so much that a
#: stack of HTML error pages bloats every row of the JSONL.
MAX_ERROR_BODY_CHARS = 2000


def raise_for_status_with_body(response: httpx.Response) -> None:
    """``raise_for_status``, but keeping the provider's explanation.

    httpx reports only the status line, so a 400 whose body says exactly what
    was wrong -- ``"`temperature` is deprecated for this model"`` -- persists as
    a bare ``400 Bad Request``. The body is the only place the reason exists;
    discard it and every provider rejection looks alike, which is how a
    one-line parameter fix turns into an afternoon of guessing.

    The re-raised error keeps the original ``response``, so ``_is_retryable``
    still sees the real status code.
    """
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = response.text[:MAX_ERROR_BODY_CHARS].strip()
        raise httpx.HTTPStatusError(
            f"{exc}\nresponse body: {body}" if body else str(exc),
            request=exc.request,
            response=exc.response,
        ) from exc


#: The params each provider's ``build_body`` actually forwards.
#:
#: Prompt frontmatter accepts any mapping, and the manifest records it verbatim,
#: so an unlisted key used to travel all the way into the run record while no
#: request ever carried it -- a manifest describing a sampling regime that never
#: existed. Refusing the key is the only honest option: silently dropping it
#: falsifies the record, and silently forwarding it would send a parameter the
#: endpoint may not accept.
SUPPORTED_PARAMS: dict[str, frozenset[str]] = {
    "anthropic": frozenset({"max_tokens", "temperature"}),
    "openai": frozenset({"max_tokens", "temperature"}),
    "openrouter": frozenset({"max_tokens", "temperature"}),
}


class UnsupportedParamError(ValueError):
    pass


def validate_params(provider: str, params: dict[str, Any], *, source: str = "") -> None:
    """Reject params the provider would not send, before any network call."""
    supported = SUPPORTED_PARAMS.get(provider)
    if supported is None:
        raise UnsupportedParamError(
            f"unknown provider {provider!r}; expected one of {', '.join(sorted(SUPPORTED_PARAMS))}"
        )
    unknown = sorted(set(params) - supported)
    if unknown:
        where = f"{source}: " if source else ""
        raise UnsupportedParamError(
            f"{where}params {', '.join(unknown)} are not supported by provider {provider!r} "
            f"(supported: {', '.join(sorted(supported))}). The request would not carry them, "
            "so the manifest would record a parameter the model never received."
        )


class ProviderSettings(BaseSettings):
    """Keys come from the environment only -- the package never reads a key file."""

    model_config = SettingsConfigDict(extra="ignore")

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    openrouter_api_key: str | None = None


class MissingAPIKeyError(RuntimeError):
    pass


class JudgeClient(Protocol):
    provider: str

    async def complete(
        self, *, system: str, user: str, model_id: str, params: dict[str, Any]
    ) -> RawCompletion: ...


class ParseFailure(BaseModel):
    message: str
    raw_text: str


def _inline(node: Any, defs: dict[str, Any]) -> Any:
    """Resolve ``$ref`` inline and strip keys strict JSON-schema mode rejects."""
    if isinstance(node, list):
        return [_inline(item, defs) for item in node]
    if not isinstance(node, dict):
        return node

    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        return _inline(defs[name], defs)

    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in {"default", "title", "$defs"}:
            continue
        out[key] = _inline(value, defs)

    if out.get("type") == "object" and "properties" in out:
        out["additionalProperties"] = False
        # Strict mode requires every property listed as required; optionality is
        # expressed by the null branch of the anyOf, which pydantic already emits.
        out["required"] = list(out["properties"].keys())
    return out


def strict_grammar() -> dict[str, Any]:
    """`JudgeResponse` as a strict, fully inlined JSON schema."""
    raw = JudgeResponse.model_json_schema()
    defs = raw.get("$defs", {})
    return _inline(raw, defs)


def resolve_key(provider: str, settings: ProviderSettings | None = None) -> str:
    settings = settings or ProviderSettings()
    key = {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "openrouter": settings.openrouter_api_key,
    }.get(provider)
    if not key:
        raise MissingAPIKeyError(
            f"no API key for provider {provider!r}: set {provider.upper()}_API_KEY in the "
            "environment (this package never reads a key file)"
        )
    return key
