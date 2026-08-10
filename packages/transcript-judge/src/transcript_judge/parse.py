"""The single place a model's raw text becomes a `JudgeResponse`.

Every provider funnels through here, and the fakes in the test-suite feed
provider-shaped payloads through the real parser rather than constructing a
`JudgeResponse` directly -- otherwise the tests would prove the parser works on
data the parser produced.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from transcript_judge.models import JudgeResponse, JudgeSpec, ParseError
from transcript_judge.prompts import PromptSchemaError, validate_response_fields

FENCE = "```"


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith(FENCE):
        return stripped
    body = stripped[len(FENCE) :]
    if body.lower().startswith("json"):
        body = body[4:]
    return body.rsplit(FENCE, 1)[0].strip() if FENCE in body else body.strip()


def parse_response(text: str, spec: JudgeSpec | None = None) -> JudgeResponse | ParseError:
    """Return a validated response, or a `ParseError` carrying the raw text.

    Never raises: a parse failure is a countable outcome that gets its own
    persisted row, not an exception that loses the sample.
    """
    candidate = _strip_fence(text)
    if not candidate:
        return ParseError(message="empty model output", raw_text=text)

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        return ParseError(message=f"invalid JSON: {exc}", raw_text=text)

    if not isinstance(payload, dict):
        return ParseError(
            message=f"expected a JSON object, got {type(payload).__name__}", raw_text=text
        )

    try:
        response = JudgeResponse.model_validate(payload)
    except ValidationError as exc:
        return ParseError(message=f"does not match the judge grammar: {exc}", raw_text=text)

    if spec is not None:
        try:
            validate_response_fields(response.model_dump(), spec)
        except PromptSchemaError as exc:
            return ParseError(message=str(exc), raw_text=text)

    return response
