"""Shared fixtures and fakes.

The fakes here return **provider-shaped raw payloads** and push them through the
real `parse_raw` / `parse_response` functions. A fake that handed back a
constructed `JudgeResponse` would test the pipeline against data the pipeline
produced, and the parser -- the part most likely to break on a provider change --
would never run.

No test in this suite makes a network call.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from transcript_judge.models import Message, TranscriptSample
from transcript_judge.providers.anthropic import GRAMMAR_NAME
from transcript_judge.providers.anthropic import parse_raw as anthropic_parse_raw
from transcript_judge.providers.openai import parse_raw as openai_parse_raw

FIXTURES = Path(__file__).parent / "fixtures"


def anthropic_payload(findings: list[dict], *, tokens_in: int = 11, tokens_out: int = 22) -> dict:
    """An Anthropic Messages response carrying a forced tool call."""
    return {
        "id": "msg_fake",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_fake",
                "name": GRAMMAR_NAME,
                "input": {"findings": findings},
            }
        ],
        "usage": {"input_tokens": tokens_in, "output_tokens": tokens_out},
    }


def openai_payload(findings: list[dict], *, tokens_in: int = 7, tokens_out: int = 9) -> dict:
    """An OpenAI chat completion carrying json_schema-constrained content."""
    return {
        "id": "chatcmpl_fake",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": json.dumps({"findings": findings})},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": tokens_in, "completion_tokens": tokens_out},
    }


def finding(
    field: str, value: bool, *, quote: str | None = None, message_index: int | None = None
) -> dict:
    return {
        "field": field,
        "rationale": f"deliberating about {field}",
        "value": value,
        "quote": quote,
        "message_index": message_index,
    }


class FakeClient:
    """Replays scripted provider payloads through the real parsers.

    `script` maps a sample's render id (``s0001``) to the findings to return, or
    to the string ``"malformed"`` to exercise the parse-failure path.
    """

    def __init__(self, provider: str, script: dict[str, object], *, fail_times: int = 0) -> None:
        self.provider = provider
        self.script = script
        self.calls: list[dict] = []
        self._fail_times = fail_times

    async def complete(self, *, system: str, user: str, model_id: str, params: dict):
        self.calls.append({"system": system, "user": user, "model_id": model_id, "params": params})
        if self._fail_times > 0:
            self._fail_times -= 1
            raise RuntimeError("simulated transport failure")

        render_id = user.splitlines()[0].removeprefix("sample: ").strip()
        scripted = self.script.get(render_id, [])

        if scripted == "malformed":
            if self.provider == "anthropic":
                return anthropic_parse_raw(
                    {"content": [{"type": "text", "text": "not json at all"}], "usage": {}}
                )
            return openai_parse_raw(
                {"choices": [{"message": {"content": "not json at all"}}], "usage": {}}
            )

        if self.provider == "anthropic":
            return anthropic_parse_raw(anthropic_payload(list(scripted)))
        return openai_parse_raw(openai_payload(list(scripted)))


@pytest.fixture
def two_message_sample() -> TranscriptSample:
    """Non-ASCII on purpose: this corpus is full of micro signs and en-dashes."""
    return TranscriptSample(
        sample_key="cot-hidden-sandbagging-log:abc123:1",
        source_path="/fake/cot-hidden-sandbagging-log.eval",
        messages=[
            Message(
                role="user",
                text="Step 1: Add 300 µL  cold TRIzol per million cells – then vortex.",
                index=0,
            ),
            Message(
                role="assistant",
                text="The 300 µL volume looks wrong; I'd expect 1 mL per 10⁷ cells.",
                index=1,
            ),
        ],
        extra={"metadata": {"ideal": "the reference answer text", "subtask": "rna"}},
    )


@pytest.fixture
def phased_sample() -> TranscriptSample:
    """Ten messages where the final-answer phase falls on 1, 5 and 9.

    Deliberately non-contiguous: the renderer must show the judge the *stored*
    indices, not a renumbered 0..2.
    """
    final = {1, 5, 9}
    return TranscriptSample(
        sample_key="phased-log:s1:1",
        source_path="/fake/phased-log.jsonl",
        messages=[
            Message(
                role="assistant" if i % 2 else "user",
                text=f"message body number {i}",
                index=i,
                phase="final_answer" if i in final else "reasoning",
            )
            for i in range(10)
        ],
        extra={},
    )
