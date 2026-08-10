"""OpenAI chat completions. The grammar is enforced by `response_format`."""

from __future__ import annotations

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

BASE_URL = "https://api.openai.com/v1/chat/completions"


class ChatCompletionsClient:
    """Shared implementation for every OpenAI-compatible endpoint."""

    provider = "openai"
    base_url = BASE_URL

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        settings: ProviderSettings | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS)
        self._settings = settings

    def extra_headers(self) -> dict[str, str]:
        return {}

    def build_body(self, *, system: str, user: str, model_id: str, params: dict[str, Any]) -> dict:
        body: dict[str, Any] = {
            "model": model_id,
            "max_tokens": params.get("max_tokens", 2048),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": GRAMMAR_NAME,
                    "strict": True,
                    "schema": strict_grammar(),
                },
            },
        }
        # Explicit-only, matching the Anthropic client. Both arms of a cross-model
        # comparison must sit in the same sampling regime, so a default applied on
        # one side and rejected on the other is a confound, not a convenience.
        if "temperature" in params:
            body["temperature"] = params["temperature"]
        return body

    async def complete(
        self, *, system: str, user: str, model_id: str, params: dict[str, Any]
    ) -> RawCompletion:
        headers = {
            "Authorization": f"Bearer {resolve_key(self.provider, self._settings)}",
            "content-type": "application/json",
        }
        headers.update(self.extra_headers())
        response = await self._client.post(
            self.base_url,
            headers=headers,
            json=self.build_body(system=system, user=user, model_id=model_id, params=params),
        )
        raise_for_status_with_body(response)
        return parse_raw(response.json())


class OpenAIClient(ChatCompletionsClient):
    pass


def parse_raw(payload: dict[str, Any]) -> RawCompletion:
    choices = payload.get("choices") or []
    text = ""
    if choices:
        text = (choices[0].get("message") or {}).get("content") or ""

    usage = payload.get("usage", {})
    return RawCompletion(
        text=text,
        tokens_in=int(usage.get("prompt_tokens", 0)),
        tokens_out=int(usage.get("completion_tokens", 0)),
        raw_json=payload,
    )
