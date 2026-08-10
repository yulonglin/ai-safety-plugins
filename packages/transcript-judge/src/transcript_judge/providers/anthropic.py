"""Anthropic Messages API. The grammar is enforced by a forced tool call."""

from __future__ import annotations

import json
from typing import Any

import httpx

from transcript_judge.models import RawCompletion
from transcript_judge.providers.base import (
    DEFAULT_TIMEOUT_SECONDS,
    GRAMMAR_NAME,
    ProviderSettings,
    raise_for_status_with_body,
    resolve_key,
    strict_grammar,
)

BASE_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicClient:
    provider = "anthropic"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        settings: ProviderSettings | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS)
        self._settings = settings

    def build_body(self, *, system: str, user: str, model_id: str, params: dict[str, Any]) -> dict:
        body: dict[str, Any] = {
            "model": model_id,
            "max_tokens": params.get("max_tokens", 2048),
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "tools": [
                {
                    "name": GRAMMAR_NAME,
                    "description": "Emit the judgement for every declared field.",
                    "input_schema": strict_grammar(),
                }
            ],
            # Forced, not merely offered: a prose reply is a parse failure we
            # would rather not have to retry through.
            "tool_choice": {"type": "tool", "name": GRAMMAR_NAME},
        }
        # Sent only when a prompt file asks for it. Defaulting to 0.0 made every
        # request carry a parameter `claude-sonnet-5` rejects outright ("`temperature`
        # is deprecated for this model", HTTP 400), and made the manifest record a
        # value the caller never chose. Absent here means provider default.
        if "temperature" in params:
            body["temperature"] = params["temperature"]
        return body

    async def complete(
        self, *, system: str, user: str, model_id: str, params: dict[str, Any]
    ) -> RawCompletion:
        response = await self._client.post(
            BASE_URL,
            headers={
                "x-api-key": resolve_key(self.provider, self._settings),
                "anthropic-version": API_VERSION,
                "content-type": "application/json",
            },
            json=self.build_body(system=system, user=user, model_id=model_id, params=params),
        )
        raise_for_status_with_body(response)
        return parse_raw(response.json())


def parse_raw(payload: dict[str, Any]) -> RawCompletion:
    """Pull the forced tool's input out of an Anthropic response body."""
    text = ""
    for block in payload.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == GRAMMAR_NAME:
            text = json.dumps(block.get("input", {}))
            break
    else:
        # No tool block: keep whatever prose came back so the parse failure is
        # inspectable rather than an empty string.
        text = "".join(
            b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text"
        )

    usage = payload.get("usage", {})
    return RawCompletion(
        text=text,
        tokens_in=int(usage.get("input_tokens", 0)),
        tokens_out=int(usage.get("output_tokens", 0)),
        raw_json=payload,
    )
