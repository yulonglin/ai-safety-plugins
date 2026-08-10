"""Fan-out, retry, persistence of every outcome, and cell-keyed resume.

No test here touches the network: `client_factory` returns a `FakeClient` that
replays provider-shaped payloads through the real parsers.
"""

from __future__ import annotations

from pathlib import Path

import anyio
import httpx
import pytest
from conftest import FakeClient, finding

from transcript_judge.models import Message, TranscriptSample
from transcript_judge.persist import RunPaths, read_jsonl
from transcript_judge.prompts import load_spec
from transcript_judge.providers import UnsupportedParamError
from transcript_judge.render import assign_render_ids
from transcript_judge.runner import (
    DEFAULT_MAX_ATTEMPTS,
    RETRYABLE_STATUS,
    describe_cells,
    run_judges,
)

FIXTURES = Path(__file__).parent / "fixtures"

ALPHA_FINDINGS = [
    finding("flags_protocol_error", True, quote="300 µL", message_index=0),
    finding("omits_safety_caveat", False),
]


def samples(n: int = 2) -> list[TranscriptSample]:
    return [
        TranscriptSample(
            sample_key=f"log:{i}:1",
            source_path="/fake/log.eval",
            messages=[
                Message(role="user", text="Add 300 µL cold TRIzol.", index=0),
                Message(role="assistant", text="That volume looks wrong.", index=1),
            ],
        )
        for i in range(n)
    ]


def go(*, samples_, specs, paths, client, **kwargs):
    return anyio.run(
        lambda: run_judges(
            samples=samples_,
            specs=specs,
            paths=paths,
            render_ids=assign_render_ids(samples_),
            client_factory=lambda provider: client,
            **kwargs,
        )
    )


def alpha_script(samples_) -> dict[str, object]:
    return {rid: ALPHA_FINDINGS for rid in assign_render_ids(samples_).values()}


# --- param validation ---------------------------------------------------------


def test_run_judges_refuses_an_unsupported_param_before_billing_any_cell(tmp_path):
    """A good spec and a bad one, with the bad one last.

    Validation is upfront rather than per-cell, so the assertion that matters is
    that the *good* judge never ran either: catching a bad param after nine of
    ten cells have been paid for would satisfy a naive "it raised" test.
    """
    samples_ = samples(2)
    specs = [
        load_spec(FIXTURES / "judge_alpha.v1.md"),
        load_spec(FIXTURES / "judge_unknown_param.v1.md"),
    ]
    client = FakeClient("anthropic", alpha_script(samples_))
    paths = RunPaths(tmp_path / "run")

    with pytest.raises(UnsupportedParamError) as caught:
        go(samples_=samples_, specs=specs, paths=paths, client=client)

    assert client.calls == []
    assert not paths.judgement_file("alpha").exists()
    message = str(caught.value)
    assert "top_p" in message
    assert "judge_unknown_param.v1.md" in message


# --- dry run -----------------------------------------------------------------


def test_dry_run_resolves_the_cell_without_a_client():
    spec = load_spec(FIXTURES / "judge_alpha.v1.md")
    (described,) = describe_cells([spec])
    assert described["judge_name"] == "alpha"
    assert described["provider"] == "anthropic"
    assert described["model_id"] == "claude-sonnet-5"
    assert described["surface"] == "full"
    assert described["params"] == {"temperature": 0.0, "max_tokens": 1024}
    assert described["fields"] == [
        "flags_protocol_error(positive_quote)",
        "omits_safety_caveat(hand_validation)",
    ]


def test_dry_run_describes_one_entry_per_cell():
    a = load_spec(FIXTURES / "judge_alpha.v1.md")
    b = load_spec(
        FIXTURES / "judge_alpha.v1.md", provider="openrouter", model_id="openai/gpt-5.6-sol"
    )
    assert [d["model_id"] for d in describe_cells([a, b])] == [
        "claude-sonnet-5",
        "openai/gpt-5.6-sol",
    ]


# --- one call per sample, never batched -------------------------------------


def test_each_sample_gets_its_own_api_call(tmp_path):
    spec = load_spec(FIXTURES / "judge_alpha.v1.md")
    rows = samples(3)
    client = FakeClient("anthropic", alpha_script(rows))
    paths = RunPaths(tmp_path / "run")

    result = go(samples_=rows, specs=[spec], paths=paths, client=client)

    assert len(client.calls) == 3
    assert result.cells[0].rows_total == 3
    assert result.cells[0].rows_parse_ok == 3
    # Each call carries exactly one sample's transcript.
    assert sorted(c["user"].splitlines()[0] for c in client.calls) == [
        "sample: s0001",
        "sample: s0002",
        "sample: s0003",
    ]


def test_the_prompt_body_is_the_system_message_and_params_are_passed_through(tmp_path):
    spec = load_spec(FIXTURES / "judge_alpha.v1.md")
    rows = samples(1)
    client = FakeClient("anthropic", alpha_script(rows))

    go(samples_=rows, specs=[spec], paths=RunPaths(tmp_path / "run"), client=client)

    (call,) = client.calls
    assert call["system"].startswith("You review one transcript")
    assert call["model_id"] == "claude-sonnet-5"
    assert call["params"] == {"temperature": 0.0, "max_tokens": 1024}


def test_the_sample_key_never_reaches_the_provider(tmp_path):
    spec = load_spec(FIXTURES / "judge_alpha.v1.md")
    rows = samples(1)
    client = FakeClient("anthropic", alpha_script(rows))

    go(samples_=rows, specs=[spec], paths=RunPaths(tmp_path / "run"), client=client)

    (call,) = client.calls
    assert "log:0:1" not in call["user"]
    assert "log:0:1" not in call["system"]


# --- every outcome is persisted ---------------------------------------------


def test_a_successful_row_records_what_was_sent_and_what_came_back(tmp_path):
    spec = load_spec(FIXTURES / "judge_alpha.v1.md")
    rows = samples(1)
    paths = RunPaths(tmp_path / "run")

    go(samples_=rows, specs=[spec], paths=paths, client=FakeClient("anthropic", alpha_script(rows)))

    (row,) = list(read_jsonl(paths.judgement_file("alpha")))
    assert row["parse_ok"] is True
    assert row["sample_key"] == "log:0:1"
    assert row["prompt_sha256"] == spec.prompt_sha256
    assert row["model_id"] == "claude-sonnet-5"
    assert row["provider"] == "anthropic"
    assert row["rendered_input"].startswith("sample: s0001\n")
    assert row["normalizer_version"] == 1
    assert row["tokens_in"] == 11
    assert row["tokens_out"] == 22
    assert [f["field"] for f in row["parsed"]["findings"]] == [
        "flags_protocol_error",
        "omits_safety_caveat",
    ]


def test_a_parse_failure_is_a_persisted_row_not_a_missing_one(tmp_path):
    spec = load_spec(FIXTURES / "judge_alpha.v1.md")
    rows = samples(1)
    paths = RunPaths(tmp_path / "run")
    client = FakeClient("anthropic", {"s0001": "malformed"})

    result = go(samples_=rows, specs=[spec], paths=paths, client=client)

    (row,) = list(read_jsonl(paths.judgement_file("alpha")))
    assert row["parse_ok"] is False
    assert row["parse_error"]
    assert row["raw_output"] == "not json at all"
    assert result.cells[0].rows_parse_failed == 1
    assert result.parse_failures == 1


def test_a_malformed_reply_is_retried_exactly_once(tmp_path):
    spec = load_spec(FIXTURES / "judge_alpha.v1.md")
    rows = samples(1)
    client = FakeClient("anthropic", {"s0001": "malformed"})

    go(samples_=rows, specs=[spec], paths=RunPaths(tmp_path / "run"), client=client)

    # More than one retry on the same prompt just buys correlated failures.
    assert len(client.calls) == 2


def test_a_non_retryable_error_is_recorded_after_a_single_attempt(tmp_path):
    spec = load_spec(FIXTURES / "judge_alpha.v1.md")
    rows = samples(1)
    paths = RunPaths(tmp_path / "run")
    client = FakeClient("anthropic", alpha_script(rows), fail_times=1)

    result = go(samples_=rows, specs=[spec], paths=paths, client=client)

    assert len(client.calls) == 1
    (row,) = list(read_jsonl(paths.judgement_file("alpha")))
    assert row["parse_ok"] is False
    assert "RuntimeError" in row["parse_error"]
    assert result.cells[0].rows_parse_failed == 1


class FlakyClient(FakeClient):
    """Raises a retryable transport error before delegating to the script."""

    def __init__(self, *args, transport_failures: int = 1, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._transport_failures = transport_failures

    async def complete(self, **kwargs):
        if self._transport_failures > 0:
            self._transport_failures -= 1
            self.calls.append(kwargs)
            raise httpx.ConnectError("simulated connection reset")
        return await super().complete(**kwargs)


def test_retryable_status_codes_are_pinned():
    assert frozenset({408, 409, 429, 500, 502, 503, 504}) == RETRYABLE_STATUS
    assert DEFAULT_MAX_ATTEMPTS == 3


def test_a_transport_error_is_retried_and_can_succeed(tmp_path):
    spec = load_spec(FIXTURES / "judge_alpha.v1.md")
    rows = samples(1)
    paths = RunPaths(tmp_path / "run")
    client = FlakyClient("anthropic", alpha_script(rows), transport_failures=1)

    result = go(samples_=rows, specs=[spec], paths=paths, client=client)

    assert len(client.calls) == 2
    (row,) = list(read_jsonl(paths.judgement_file("alpha")))
    assert row["parse_ok"] is True
    assert row["attempt"] == 2
    assert result.cells[0].rows_parse_ok == 1


# --- resume ------------------------------------------------------------------


def test_a_second_run_skips_completed_samples_and_makes_no_calls(tmp_path):
    spec = load_spec(FIXTURES / "judge_alpha.v1.md")
    rows = samples(2)
    paths = RunPaths(tmp_path / "run")

    go(samples_=rows, specs=[spec], paths=paths, client=FakeClient("anthropic", alpha_script(rows)))

    second_client = FakeClient("anthropic", alpha_script(rows))
    result = go(samples_=rows, specs=[spec], paths=paths, client=second_client)

    assert second_client.calls == []
    assert result.cells[0].rows_skipped == 2
    assert result.cells[0].rows_total == 0
    assert len(list(read_jsonl(paths.judgement_file("alpha")))) == 2


def test_a_failed_row_is_retried_on_resume(tmp_path):
    spec = load_spec(FIXTURES / "judge_alpha.v1.md")
    rows = samples(1)
    paths = RunPaths(tmp_path / "run")

    go(
        samples_=rows,
        specs=[spec],
        paths=paths,
        client=FakeClient("anthropic", {"s0001": "malformed"}),
    )

    second = FakeClient("anthropic", alpha_script(rows))
    result = go(samples_=rows, specs=[spec], paths=paths, client=second)

    assert len(second.calls) == 1
    assert result.cells[0].rows_skipped == 0
    assert result.cells[0].rows_parse_ok == 1
    # Append-only: the failed row is still on disk beside the successful one.
    persisted = list(read_jsonl(paths.judgement_file("alpha")))
    assert [r["parse_ok"] for r in persisted] == [False, True]


def test_a_second_model_behind_the_same_prompt_is_not_skipped(tmp_path):
    """The failure this guards against silently halves a two-model run."""
    anthropic_spec = load_spec(FIXTURES / "judge_alpha.v1.md")
    openrouter_spec = load_spec(
        FIXTURES / "judge_alpha.v1.md", provider="openrouter", model_id="openai/gpt-5.6-sol"
    )
    rows = samples(2)
    paths = RunPaths(tmp_path / "run")

    go(
        samples_=rows,
        specs=[anthropic_spec],
        paths=paths,
        client=FakeClient("anthropic", alpha_script(rows)),
    )

    second = FakeClient("openai", alpha_script(rows))
    result = go(samples_=rows, specs=[openrouter_spec], paths=paths, client=second)

    assert len(second.calls) == 2
    assert result.cells[0].rows_skipped == 0
    assert result.cells[0].rows_parse_ok == 2

    persisted = list(read_jsonl(paths.judgement_file("alpha")))
    assert len(persisted) == 4
    assert sorted({r["model_id"] for r in persisted}) == [
        "claude-sonnet-5",
        "openai/gpt-5.6-sol",
    ]
    # One file per prompt, holding both cells interleaved.
    assert sorted(p.name for p in paths.judgements_dir.iterdir()) == ["alpha.jsonl"]


def test_both_cells_are_reported_separately_in_one_run(tmp_path):
    anthropic_spec = load_spec(FIXTURES / "judge_alpha.v1.md")
    openrouter_spec = load_spec(
        FIXTURES / "judge_alpha.v1.md", provider="openrouter", model_id="openai/gpt-5.6-sol"
    )
    rows = samples(2)
    client = FakeClient("anthropic", alpha_script(rows))

    result = go(
        samples_=rows,
        specs=[anthropic_spec, openrouter_spec],
        paths=RunPaths(tmp_path / "run"),
        client=client,
    )

    assert len(result.cells) == 2
    assert [c.model_id for c in result.cells] == ["claude-sonnet-5", "openai/gpt-5.6-sol"]
    assert all(c.rows_parse_ok == 2 for c in result.cells)


# --- the final_answer fallback is counted, not hidden ------------------------


def test_samples_that_fell_back_to_the_last_assistant_are_counted(tmp_path):
    spec = load_spec(FIXTURES / "judge_alpha.v1.md").model_copy(update={"surface": "final_answer"})
    rows = samples(2)
    client = FakeClient("anthropic", alpha_script(rows))

    result = go(samples_=rows, specs=[spec], paths=RunPaths(tmp_path / "run"), client=client)

    # Neither sample carries a message_phase, which is true of every real
    # ProtocolQA log surveyed on 2026-08-09.
    assert result.final_answer_fallback_samples == 2
