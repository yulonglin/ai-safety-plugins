"""Request-body and error-surfacing contracts for the provider clients.

These exist because a `temperature` default that no prompt file asked for
reached a live run and 400'd every Anthropic call ("`temperature` is deprecated
for this model"), and the failure persisted as a bare "400 Bad Request" because
`raise_for_status` throws the explanation away. Both halves are pinned here.
"""

from __future__ import annotations

import httpx
import pytest

from transcript_judge.cli import BUILTIN_MERGE_PROMPT
from transcript_judge.prompts import load_spec
from transcript_judge.providers.anthropic import AnthropicClient
from transcript_judge.providers.base import (
    SUPPORTED_PARAMS,
    UnsupportedParamError,
    raise_for_status_with_body,
    validate_params,
)
from transcript_judge.providers.openai import ChatCompletionsClient
from transcript_judge.providers.openrouter import OpenRouterClient

BODY_KWARGS = {"system": "sys", "user": "usr", "model_id": "m-1"}

# Every client whose body must treat `temperature` as explicit-only. OpenRouter is
# listed separately from its base class: it is the arm that *accepted* temperature,
# so "the other provider already omits it" is not evidence about this one.
CLIENTS = [AnthropicClient, ChatCompletionsClient, OpenRouterClient]


@pytest.mark.parametrize("client_cls", CLIENTS)
def test_temperature_absent_when_params_omit_it(client_cls):
    """Provider default, not a silent 0.0.

    Both arms of a cross-model comparison must sit in the same sampling regime;
    a default applied here and rejected there is a confound.
    """
    body = client_cls().build_body(**BODY_KWARGS, params={"max_tokens": 2000})
    assert "temperature" not in body


@pytest.mark.parametrize("client_cls", CLIENTS)
def test_temperature_forwarded_verbatim_when_asked_for(client_cls):
    """A prompt file that pins temperature still gets exactly that value.

    0.3 rather than 0.0: a legal-but-unusual value fails against both a dropped
    parameter and a hardcoded default, where 0.0 would silently pass against the
    old `params.get("temperature", 0.0)`.
    """
    body = client_cls().build_body(**BODY_KWARGS, params={"max_tokens": 2000, "temperature": 0.3})
    assert body["temperature"] == 0.3


@pytest.mark.parametrize("client_cls", CLIENTS)
def test_max_tokens_forwarded_verbatim(client_cls):
    body = client_cls().build_body(**BODY_KWARGS, params={"max_tokens": 1234})
    assert body["max_tokens"] == 1234


def test_the_real_builtin_merge_prompt_sends_no_temperature():
    """The file the CLI actually loads, through the body builder it actually uses.

    The unit tests above pin the clients against hand-written params dicts, which
    says nothing about what the shipped prompt *declares*. `merge_equivalence.v1.md`
    carried `temperature: 0.0` in its frontmatter long after the clients stopped
    defaulting it, and the e2e run never caught it because one distinct positive
    label means zero merge calls. `max_tokens` is asserted alongside so an empty
    or unparsed params dict cannot satisfy the temperature assertion vacuously.
    """
    spec = load_spec(BUILTIN_MERGE_PROMPT)

    assert "temperature" not in spec.params
    assert spec.params["max_tokens"] == 600

    body = AnthropicClient().build_body(
        system=spec.prompt_text,
        user="Label A:\nx\n\nLabel B:\ny",
        model_id="claude-sonnet-5",
        params=spec.params,
    )

    assert "temperature" not in body
    assert body["max_tokens"] == 600


@pytest.mark.parametrize("provider", ["anthropic", "openai", "openrouter"])
def test_an_unsupported_param_is_refused_before_any_network_call(provider):
    with pytest.raises(UnsupportedParamError) as caught:
        validate_params(provider, {"max_tokens": 500, "top_p": 0.9}, source="judge_foo.v1.md")

    message = str(caught.value)
    assert "top_p" in message
    assert "judge_foo.v1.md" in message
    # The supported set is named, so the message says what to do, not just what broke.
    assert "max_tokens" in message
    assert "temperature" in message


@pytest.mark.parametrize("provider", ["anthropic", "openai", "openrouter"])
def test_supported_params_are_accepted(provider):
    """The refusal must not be a blanket one -- otherwise it passes for the wrong reason."""
    validate_params(provider, {"max_tokens": 500, "temperature": 0.3})


def test_every_declared_supported_param_is_actually_forwarded():
    """Anti-drift, in the direction the declaration could lie.

    `SUPPORTED_PARAMS` lives beside the contract rather than inside each
    `build_body`, so it can drift into promising a param the body never sends --
    exactly the recorded-but-not-sent falsehood the validation exists to stop.
    """
    for client_cls in CLIENTS:
        provider = client_cls.provider
        for name, value in [("max_tokens", 1234), ("temperature", 0.3)]:
            body = client_cls().build_body(**BODY_KWARGS, params={name: value})
            assert body[name] == value, f"{provider} declares {name} but does not send it"
        assert set(SUPPORTED_PARAMS[provider]) == {"max_tokens", "temperature"}


def test_error_body_reaches_the_raised_message():
    """The provider's reason is the whole point of the exception."""
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(
        400,
        json={"type": "error", "error": {"message": "`temperature` is deprecated for this model"}},
        request=request,
    )

    with pytest.raises(httpx.HTTPStatusError) as caught:
        raise_for_status_with_body(response)

    message = str(caught.value)
    assert "`temperature` is deprecated for this model" in message
    assert "400" in message


def test_error_keeps_status_code_so_retry_logic_still_works():
    """`_is_retryable` reads `exc.response.status_code`; re-raising must not lose it."""
    request = httpx.Request("POST", "https://example.invalid/v1")
    response = httpx.Response(429, text="slow down", request=request)

    with pytest.raises(httpx.HTTPStatusError) as caught:
        raise_for_status_with_body(response)

    assert caught.value.response.status_code == 429


def test_oversized_error_body_is_truncated():
    request = httpx.Request("POST", "https://example.invalid/v1")
    response = httpx.Response(500, text="x" * 50_000, request=request)

    with pytest.raises(httpx.HTTPStatusError) as caught:
        raise_for_status_with_body(response)

    assert len(str(caught.value)) < 5_000


def test_success_does_not_raise():
    request = httpx.Request("POST", "https://example.invalid/v1")
    raise_for_status_with_body(httpx.Response(200, json={"ok": True}, request=request))
