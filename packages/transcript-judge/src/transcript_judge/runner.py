"""Concurrent judge fan-out: one API call per sample per cell, never batched.

Batching several samples into one prompt leaks context between them, collapses
the per-sample rationale, and turns one parse failure into many lost rows. So
the loop is embarrassingly parallel instead, bounded by a `CapacityLimiter`.

A row is appended for **every** attempt outcome, including total failure. A
sample that never parsed is a `parse_ok: false` row with the error text, not an
absence -- absences are indistinguishable from work never done.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from typing import Any

import anyio
import httpx
from pydantic import BaseModel, Field

from transcript_judge.models import (
    JudgeCell,
    JudgementRow,
    JudgeSpec,
    ParseError,
    TranscriptSample,
)
from transcript_judge.normalize import NORMALIZER_VERSION
from transcript_judge.parse import parse_response
from transcript_judge.persist import RunPaths, append_jsonl, load_completed, utc_now
from transcript_judge.providers import get_client, validate_params
from transcript_judge.render import RenderedSample, assert_blinded, render_sample

DEFAULT_CONCURRENCY = 8
DEFAULT_MAX_ATTEMPTS = 3
RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})


class CellStats(BaseModel):
    judge_name: str
    prompt_sha256: str
    model_id: str
    provider: str
    rows_total: int = 0
    rows_parse_ok: int = 0
    rows_parse_failed: int = 0
    rows_skipped: int = 0
    tokens_in: int = 0
    tokens_out: int = 0

    @property
    def cell(self) -> JudgeCell:
        return JudgeCell(
            judge_name=self.judge_name,
            prompt_sha256=self.prompt_sha256,
            model_id=self.model_id,
        )


class RunResult(BaseModel):
    cells: list[CellStats] = Field(default_factory=list)
    final_answer_fallback_samples: int = 0

    @property
    def parse_failures(self) -> int:
        return sum(c.rows_parse_failed for c in self.cells)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS
    return isinstance(exc, httpx.TransportError | httpx.TimeoutException)


async def _backoff(attempt: int, rng: random.Random) -> None:
    delay = min(30.0, 0.5 * (2 ** (attempt - 1)))
    await anyio.sleep(delay * (0.5 + rng.random()))


def describe_cells(specs: list[JudgeSpec]) -> list[dict[str, Any]]:
    """What `--dry-run` prints: the resolved cell for every spec, no network."""
    return [
        {
            "judge_name": spec.name,
            "prompt_path": spec.prompt_path,
            "prompt_sha256": spec.prompt_sha256,
            "provider": spec.provider,
            "model_id": spec.model_id,
            "surface": spec.surface,
            "params": spec.params,
            "fields": [f"{f.name}({f.evidence_mode})" for f in spec.schema_fields],
        }
        for spec in specs
    ]


async def _judge_one(
    *,
    spec: JudgeSpec,
    sample: TranscriptSample,
    rendered: RenderedSample,
    client: Any,
    paths: RunPaths,
    stats: CellStats,
    max_attempts: int,
    rng: random.Random,
) -> None:
    last_error = "no attempt completed"
    raw_text = ""
    tokens_in = tokens_out = 0
    parsed: dict[str, Any] | None = None
    parse_ok = False
    attempt = 0
    parse_retries_left = 1

    while attempt < max_attempts:
        attempt += 1
        try:
            completion = await client.complete(
                system=spec.prompt_text,
                user=rendered.text,
                model_id=spec.model_id,
                params=spec.params,
            )
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if _is_retryable(exc) and attempt < max_attempts:
                await _backoff(attempt, rng)
                continue
            break

        raw_text = completion.text
        tokens_in, tokens_out = completion.tokens_in, completion.tokens_out
        result = parse_response(raw_text, spec)

        if isinstance(result, ParseError):
            last_error = result.message
            # A malformed reply is retried once with the same prompt; more than
            # that just buys correlated failures at full price.
            if parse_retries_left > 0 and attempt < max_attempts:
                parse_retries_left -= 1
                continue
            break

        parsed = result.model_dump()
        parse_ok = True
        break

    row = JudgementRow(
        sample_key=sample.sample_key,
        judge_name=spec.name,
        prompt_sha256=spec.prompt_sha256,
        model_id=spec.model_id,
        provider=spec.provider,
        surface=spec.surface,
        rendered_input=rendered.text,
        raw_output=raw_text,
        parsed=parsed,
        parse_ok=parse_ok,
        parse_error=None if parse_ok else last_error,
        attempt=attempt,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        timestamp_utc=utc_now(),
        normalizer_version=NORMALIZER_VERSION,
    )
    append_jsonl(paths.judgement_file(spec.name), row.model_dump())

    stats.rows_total += 1
    stats.tokens_in += tokens_in
    stats.tokens_out += tokens_out
    if parse_ok:
        stats.rows_parse_ok += 1
    else:
        stats.rows_parse_failed += 1


async def run_judges(
    *,
    samples: list[TranscriptSample],
    specs: list[JudgeSpec],
    paths: RunPaths,
    render_ids: dict[str, str],
    include_metadata: list[str] | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    client_factory: Callable[[str], Any] = get_client,
    seed: int = 0,
) -> RunResult:
    """Fan every (sample, cell) pair out concurrently and persist each outcome."""
    # Upfront, and here rather than only in the CLI: the invariant is that no
    # request ever leaves with a param the manifest will claim it carried, and an
    # invariant enforced only at the call sites that happen to exist today is one
    # the next caller silently breaks. Every spec is checked before the first
    # cell runs, so a bad param on the last judge cannot surface after the first
    # nine have already been billed.
    for spec in specs:
        validate_params(spec.provider, spec.params, source=spec.prompt_path)

    paths.ensure()
    limiter = anyio.CapacityLimiter(concurrency)
    rng = random.Random(seed)
    result = RunResult()
    fallback_samples: set[str] = set()

    for spec in specs:
        stats = CellStats(
            judge_name=spec.name,
            prompt_sha256=spec.prompt_sha256,
            model_id=spec.model_id,
            provider=spec.provider,
        )
        completed = load_completed(paths.judgement_file(spec.name))
        client = client_factory(spec.provider)

        pending: list[tuple[TranscriptSample, RenderedSample]] = []
        for sample in samples:
            if (sample.sample_key, spec.prompt_sha256, spec.model_id) in completed:
                stats.rows_skipped += 1
                continue
            rendered = render_sample(
                sample,
                surface=spec.surface,
                render_id=render_ids[sample.sample_key],
                include_metadata=include_metadata,
            )
            assert_blinded(rendered.text, sample)
            if rendered.final_answer_fallback:
                fallback_samples.add(sample.sample_key)
            pending.append((sample, rendered))

        async def _guarded(
            sample: TranscriptSample,
            rendered: RenderedSample,
            spec: JudgeSpec = spec,
            stats: CellStats = stats,
            client: Any = client,
        ) -> None:
            async with limiter:
                await _judge_one(
                    spec=spec,
                    sample=sample,
                    rendered=rendered,
                    client=client,
                    paths=paths,
                    stats=stats,
                    max_attempts=max_attempts,
                    rng=rng,
                )

        async with anyio.create_task_group() as tg:
            for sample, rendered in pending:
                tg.start_soon(_guarded, sample, rendered)

        result.cells.append(stats)

    result.final_answer_fallback_samples = len(fallback_samples)
    return result
