"""`tj` -- the command line over the pipeline.

Two conventions hold across every subcommand:

* **Failures are printed, not swallowed.** Any command that prints results also
  prints the parse-failure and unresolved-quote counts, so a degraded run cannot
  be mistaken for a clean one by reading the happy path.
* **Blinding violations exit non-zero.** They are not warnings. A run that
  handed a judge the reference answer has not measured what it claims to.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Annotated, Any

import anyio
from cyclopts import App, Parameter

from transcript_judge import __version__
from transcript_judge.artifact import build_overlap, render_html
from transcript_judge.cluster import cache_token_totals, cluster_labels
from transcript_judge.labels import derive_labels, verify_spans
from transcript_judge.loaders import load as load_transcripts
from transcript_judge.models import LabelRow, TranscriptSample
from transcript_judge.normalize import NORMALIZER_VERSION, sha256_file
from transcript_judge.persist import (
    RunPaths,
    append_jsonl,
    read_json,
    read_jsonl,
    read_row_at,
    row_id,
    split_row_id,
    transcripts_sha256,
    utc_now,
    write_json,
)
from transcript_judge.prompts import PromptSchemaError, load_spec, parse_model_ref
from transcript_judge.providers import UnsupportedParamError, get_client, validate_params
from transcript_judge.render import BlindingViolation, assign_render_ids, check_metadata_keys
from transcript_judge.runner import DEFAULT_CONCURRENCY, describe_cells, run_judges
from transcript_judge.stats import StatsReport, agreement

app = App(name="tj", help="Transcript review with LLM judges.", version=__version__)

BUILTIN_MERGE_PROMPT = Path(__file__).parent / "prompts_builtin" / "merge_equivalence.v1.md"

EXIT_BLINDING = 2
EXIT_SCHEMA = 3
EXIT_USAGE = 4
EXIT_PARAMS = 5


def _fail(message: str, code: int) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def _load_samples(paths: RunPaths) -> list[TranscriptSample]:
    """Sorted by ``sample_key`` so that ``--limit`` selects the same subset every run,
    and the same order ``assign_render_ids`` numbers against. File order is whatever the
    upstream loader enumerated and is not stable across inputs."""
    rows = [TranscriptSample.model_validate(row) for row in read_jsonl(paths.transcripts)]
    return sorted(rows, key=lambda s: s.sample_key)


def _load_labels(paths: RunPaths) -> list[LabelRow]:
    return [LabelRow.model_validate(row) for row in read_jsonl(paths.labels)]


def _print_health(manifest: dict[str, Any]) -> None:
    """Printed by every command that reports results. Never omitted on success."""
    cells = manifest.get("judge_cells", [])
    failures = sum(c.get("rows_parse_failed", 0) for c in cells)
    unresolved = sum(c.get("labels_unresolved", 0) for c in cells)
    corrected = manifest.get("message_index_corrected_count", 0)
    print(
        f"\nhealth: parse failures {failures} · unresolved quotes {unresolved} "
        f"· message indices corrected {corrected} · blinded {manifest.get('blinded', True)}"
    )
    if manifest.get("final_answer_fallback_samples"):
        print(
            f"note: {manifest['final_answer_fallback_samples']} sample(s) had no message_phase "
            "marker; the final_answer surface fell back to the last assistant message."
        )


@app.command
def load(
    paths: list[str],
    *,
    run: Annotated[
        str | None, Parameter(help="Run directory. Defaults to runs/<timestamp>.")
    ] = None,
    format: str = "auto",
) -> None:
    """Load transcripts into a run directory."""
    run_id = Path(run).name if run else datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_paths = RunPaths(Path(run) if run else Path("runs") / run_id).ensure()

    stats: dict[str, int] = {}
    samples: list[TranscriptSample] = []
    for path in paths:
        samples.extend(load_transcripts(path, format=format, stats=stats))

    if not samples:
        _fail(f"no samples loaded from {', '.join(paths)}", EXIT_USAGE)

    rows = [s.model_dump() for s in samples]
    run_paths.transcripts.unlink(missing_ok=True)
    for row in rows:
        append_jsonl(run_paths.transcripts, row)

    render_ids = assign_render_ids(samples)
    manifest = {
        "run_id": run_id,
        "created_utc": utc_now(),
        "package_version": __version__,
        "normalizer_version": NORMALIZER_VERSION,
        "input_paths": list(paths),
        "input_data_sha256": {p: sha256_file(p) for p in paths if Path(p).is_file()},
        "transcripts_sha256": transcripts_sha256(rows),
        "n_samples": len(samples),
        "n_messages": sum(len(s.messages) for s in samples),
        "non_text_blocks_elided": stats.get("non_text_blocks_elided", 0),
        "sample_id_map": render_ids,
        "judge_cells": [],
        "blinded": True,
    }
    write_json(run_paths.manifest, manifest)

    print(f"run: {run_paths.root}")
    print(f"samples: {len(samples)} · messages: {manifest['n_messages']}")
    print(f"transcripts_sha256: {manifest['transcripts_sha256']}")
    print(f"non-text blocks elided: {manifest['non_text_blocks_elided']}")


@app.command
def run(
    *,
    run: str,
    judge: list[str],
    model: list[str] | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    limit: int | None = None,
    dry_run: bool = False,
    include_metadata: list[str] | None = None,
) -> None:
    """Fan judges out over the loaded transcripts."""
    run_paths = RunPaths(Path(run))
    if not run_paths.manifest.exists():
        _fail(f"{run} has no manifest.json; run `tj load` first", EXIT_USAGE)

    try:
        check_metadata_keys(include_metadata or [])
    except BlindingViolation as exc:
        _fail(str(exc), EXIT_BLINDING)

    refs = model or []
    try:
        specs = []
        for prompt_path in judge:
            if refs:
                for ref in refs:
                    provider, model_id = parse_model_ref(ref)
                    specs.append(load_spec(prompt_path, provider=provider, model_id=model_id))
            else:
                specs.append(load_spec(prompt_path))
    except PromptSchemaError as exc:
        _fail(str(exc), EXIT_SCHEMA)

    # Before the dry run, not merely before the fan-out: a dry run that prints a
    # param the provider would silently drop is the falsehood we are preventing.
    try:
        for spec in specs:
            validate_params(spec.provider, spec.params, source=spec.prompt_path)
    except UnsupportedParamError as exc:
        _fail(str(exc), EXIT_PARAMS)

    if dry_run:
        print(f"dry run: {len(specs)} judge cell(s), no network calls\n")
        for cell in describe_cells(specs):
            print(f"  {cell['judge_name']} @ {cell['prompt_sha256'][:12]}")
            print(f"    provider : {cell['provider']}")
            print(f"    model    : {cell['model_id']}")
            print(f"    surface  : {cell['surface']}")
            print(f"    params   : {cell['params']}")
            print(f"    fields   : {', '.join(cell['fields'])}")
        return

    samples = _load_samples(run_paths)
    if limit is not None:
        samples = samples[:limit]
    manifest = read_json(run_paths.manifest)
    render_ids = manifest.get("sample_id_map") or assign_render_ids(samples)

    try:
        result = anyio.run(
            lambda: run_judges(
                samples=samples,
                specs=specs,
                paths=run_paths,
                render_ids=render_ids,
                include_metadata=include_metadata,
                concurrency=concurrency,
            )
        )
    except BlindingViolation as exc:
        _fail(str(exc), EXIT_BLINDING)

    by_cell = {
        (c["judge_name"], c["prompt_sha256"], c["model_id"]): c
        for c in manifest.get("judge_cells", [])
    }
    for spec, cell_stats in zip(specs, result.cells, strict=True):
        key = (spec.name, spec.prompt_sha256, spec.model_id)
        entry = by_cell.setdefault(key, {})
        entry.update(
            {
                "name": spec.name,
                "judge_name": spec.name,
                "prompt_path": spec.prompt_path,
                "prompt_sha256": spec.prompt_sha256,
                "provider": spec.provider,
                "model_id": spec.model_id,
                "surface": spec.surface,
                "params": spec.params,
                "fields": [
                    {"name": f.name, "evidence_mode": f.evidence_mode} for f in spec.schema_fields
                ],
                "rows_total": cell_stats.rows_total,
                "rows_parse_ok": cell_stats.rows_parse_ok,
                "rows_parse_failed": cell_stats.rows_parse_failed,
                "rows_skipped": cell_stats.rows_skipped,
                "tokens_in": cell_stats.tokens_in,
                "tokens_out": cell_stats.tokens_out,
            }
        )

    manifest["judge_cells"] = list(by_cell.values())
    manifest["limit"] = limit
    manifest["judged_sample_keys"] = sorted({s.sample_key for s in samples})
    manifest["concurrency"] = concurrency
    manifest["include_metadata"] = include_metadata or []
    manifest["final_answer_fallback_samples"] = result.final_answer_fallback_samples
    write_json(run_paths.manifest, manifest)

    for cell_stats in result.cells:
        print(
            f"{cell_stats.judge_name} @ {cell_stats.prompt_sha256[:12]} / {cell_stats.model_id}: "
            f"{cell_stats.rows_parse_ok} ok · {cell_stats.rows_parse_failed} parse failures "
            f"· {cell_stats.rows_skipped} skipped (already complete)"
        )
    _print_health(manifest)


@app.command
def labels(*, run: str) -> None:
    """Derive grounded label rows from the judgement files."""
    run_paths = RunPaths(Path(run))
    manifest = read_json(run_paths.manifest)
    samples_by_key = {s.sample_key: s for s in _load_samples(run_paths)}

    field_modes: dict[tuple[str, str], dict[str, str]] = {}
    for cell in manifest.get("judge_cells", []):
        modes = {f["name"]: f["evidence_mode"] for f in cell.get("fields", [])}
        field_modes[(cell["judge_name"], cell["prompt_sha256"])] = modes

    # Offsets are taken from the file itself, not from a re-serialisation: the
    # row id has to seek back to these exact bytes for `tj show`.
    rows: list[dict] = []
    ids: list[str] = []
    for path in sorted(run_paths.judgements_dir.glob("*.jsonl")):
        offset = 0
        with open(path, "rb") as handle:
            for raw in handle:
                text = raw.decode("utf-8").strip()
                if text:
                    rows.append(json.loads(text))
                    ids.append(row_id(path.stem, offset))
                offset += len(raw)

    derived, stats = derive_labels(
        rows=rows,
        samples_by_key=samples_by_key,
        field_modes=field_modes,  # type: ignore[arg-type]
        row_ids=ids,
    )

    run_paths.labels.unlink(missing_ok=True)
    for label in derived:
        append_jsonl(run_paths.labels, label.model_dump())

    problems = verify_spans(derived, samples_by_key)

    for cell in manifest.get("judge_cells", []):
        cell_labels = [
            lab
            for lab in derived
            if lab.judge_name == cell["judge_name"]
            and lab.prompt_sha256 == cell["prompt_sha256"]
            and lab.model_id == cell["model_id"]
        ]
        cell["labels_total"] = len(cell_labels)
        cell["labels_unresolved"] = sum(
            1
            for lab in cell_labels
            if lab.value and lab.evidence_mode == "positive_quote" and not lab.resolved
        )
        tiers: dict[str, int] = {}
        for lab in cell_labels:
            if lab.value and lab.evidence_mode == "positive_quote":
                tiers[lab.resolution_tier] = tiers.get(lab.resolution_tier, 0) + 1
        cell["resolution_tier_counts"] = tiers

    manifest["message_index_corrected_count"] = stats.message_index_corrected_count
    manifest["labels_hand_validation"] = stats.labels_hand_validation
    write_json(run_paths.manifest, manifest)

    print(f"labels: {stats.labels_total} ({stats.labels_positive} positive)")
    print(f"resolution tiers: {stats.resolution_tier_counts}")
    print(f"hand-validation fields (not quote-grounded): {stats.labels_hand_validation}")
    if problems:
        print(f"\nSPAN INVARIANT VIOLATIONS: {len(problems)}", file=sys.stderr)
        for problem in problems[:10]:
            print(f"  {problem}", file=sys.stderr)
        raise SystemExit(1)
    _print_health(manifest)


@app.command
def show(label_id: str, *, run: str, part: str = "all") -> None:
    """Show the input, output or excerpt behind one label."""
    run_paths = RunPaths(Path(run))
    match = next(
        (lab for lab in _load_labels(run_paths) if lab.label_id == label_id),
        None,
    )
    if match is None:
        _fail(f"no label {label_id!r} in {run}", EXIT_USAGE)

    filename, offset = split_row_id(match.judgement_row_id)
    row = read_row_at(run_paths.judgements_dir / filename, offset)

    if part in {"input", "all"}:
        print("=== rendered input (exactly what was sent) ===")
        print(row["rendered_input"])
    if part in {"output", "all"}:
        print("=== raw model output ===")
        print(row["raw_output"])
    if part in {"excerpt", "all"}:
        print("=== excerpt ===")
        print(f"judge_quote    : {match.judge_quote!r}")
        print(f"source_excerpt : {match.source_excerpt!r}")
        print(
            f"span           : message {match.message_index} "
            f"[{match.char_start}, {match.char_end}) {match.offset_unit}"
        )
        print(f"resolution     : {match.resolution_tier} (resolved={match.resolved})")


@app.command
def cluster(*, run: str, merge_prompt: str | None = None, model: str | None = None) -> None:
    """Group equivalent labels with the merge judge."""
    run_paths = RunPaths(Path(run))
    manifest = read_json(run_paths.manifest)
    prompt_path = Path(merge_prompt) if merge_prompt else BUILTIN_MERGE_PROMPT

    try:
        provider, model_id = parse_model_ref(model) if model else (None, None)
        spec = load_spec(prompt_path, provider=provider, model_id=model_id)
    except PromptSchemaError as exc:
        _fail(str(exc), EXIT_SCHEMA)

    try:
        validate_params(spec.provider, spec.params, source=spec.prompt_path)
    except UnsupportedParamError as exc:
        _fail(str(exc), EXIT_PARAMS)

    cache_path = run_paths.clusters_dir / "pairwise_cache.jsonl"
    assignments, stats = anyio.run(
        lambda: cluster_labels(
            labels=_load_labels(run_paths),
            cache_path=cache_path,
            merge_prompt_text=spec.prompt_text,
            merge_prompt_sha256=spec.prompt_sha256,
            model_id=spec.model_id,
            client_factory=get_client,
            provider=spec.provider,
            params=spec.params,
        )
    )

    write_json(
        run_paths.clusters_dir / "assignments.json",
        [a.model_dump() for a in assignments],
    )
    write_json(run_paths.clusters_dir / "contradictions.json", stats.contradictions)

    manifest["cluster"] = {
        "merge_prompt_sha256": stats.merge_prompt_sha256,
        "model_id": stats.model_id,
        "n_distinct_labels": stats.n_distinct_labels,
        "n_pairs": stats.n_pairs,
        "n_pairs_cached": stats.n_pairs_cached,
        "n_clusters": stats.n_clusters,
        "contradictory_triads": stats.contradictory_triads,
        "parse_failures": stats.parse_failures,
        # Two scopes, named rather than merged: a warm rerun spends nothing, so
        # the invocation figure goes to zero while the cumulative one -- summed
        # from the append-only cache rows -- still reports what the run cost.
        "tokens_this_invocation": {"in": stats.tokens_in, "out": stats.tokens_out},
        "tokens_cumulative_from_cache": cache_token_totals(cache_path),
    }
    write_json(run_paths.manifest, manifest)

    cumulative = manifest["cluster"]["tokens_cumulative_from_cache"]
    print(f"clusters: {stats.n_clusters} from {stats.n_distinct_labels} distinct labels")
    print(f"pairs: {stats.n_pairs} ({stats.n_pairs_cached} served from cache)")
    print(f"contradictory triads: {stats.contradictory_triads}")
    print(f"merge-judge parse failures: {stats.parse_failures}")
    print(
        f"merge tokens: {stats.tokens_in} in / {stats.tokens_out} out this invocation; "
        f"{cumulative['tokens_in']} in / {cumulative['tokens_out']} out cumulative "
        f"over {cumulative['rows']} cached pairs"
    )
    _print_health(manifest)


@app.command
def stats(*, run: str, seed: int = 20260809, permutations: int = 10_000) -> None:
    """Agreement between models, each figure with its chance-agreement null."""
    run_paths = RunPaths(Path(run))
    manifest = read_json(run_paths.manifest)

    if not manifest.get("blinded", True):
        _fail(
            "this run is marked blinded=false: a judge saw material outside the blinding "
            "perimeter, so agreement figures would not mean what they appear to. Refusing "
            "to print them.",
            EXIT_BLINDING,
        )

    all_labels = _load_labels(run_paths)
    models = sorted({lab.model_id for lab in all_labels})
    constructs = sorted({lab.label for lab in all_labels if lab.evidence_mode == "positive_quote"})

    report = StatsReport(permutation_seed=seed, n_permutations=permutations)
    for construct in constructs:
        for model_a, model_b in combinations(models, 2):
            report.results.append(
                agreement(
                    all_labels,
                    construct,
                    model_a,
                    model_b,
                    seed=seed,
                    n_permutations=permutations,
                )
            )

    print(f"models: {', '.join(models) or '(none)'}")
    if len(models) < 2:
        print("fewer than two models: no cross-model agreement to report")
    else:
        n_pairs = len(models) * (len(models) - 1) // 2
        print(f"model pairs compared: {n_pairs} (every unordered pair, per construct)")
    for result in report.results:
        print(f"\n{result.describe()}")
        print(
            f"  paired samples {result.n_paired} · excluded as unqueried by one model "
            f"{result.n_excluded_unqueried} (missing, not counted as negative)"
        )
        if result.permutation_p is not None:
            print(
                f"  permutation null p={result.permutation_p:.4f} "
                f"({result.n_permutations} draws, seed {result.permutation_seed})"
            )
    print(f"\n{report.interval_scope}")

    manifest["stats"] = {"permutation_seed": seed, "n_permutations": permutations}
    write_json(run_paths.manifest, manifest)
    _print_health(manifest)


@app.command
def artifact(*, run: str) -> None:
    """Write overlap.json and a self-contained overlap.html."""
    run_paths = RunPaths(Path(run)).ensure()
    manifest = read_json(run_paths.manifest)
    all_labels = _load_labels(run_paths)

    rationales: dict[str, str] = {}
    for label in all_labels:
        filename, offset = split_row_id(label.judgement_row_id)
        path = run_paths.judgements_dir / filename
        if not path.exists():
            continue
        row = read_row_at(path, offset)
        for finding in (row.get("parsed") or {}).get("findings", []):
            if finding["field"] == label.label:
                rationales[label.label_id] = finding.get("rationale", "")

    overlap = build_overlap(
        labels=all_labels,
        run_id=manifest["run_id"],
        blinded=manifest.get("blinded", True),
        rationales=rationales,
    )
    write_json(run_paths.artifact_dir / "overlap.json", overlap)
    (run_paths.artifact_dir / "overlap.html").write_text(render_html(overlap), encoding="utf-8")

    print(f"overlap.json  : {run_paths.artifact_dir / 'overlap.json'}")
    print(f"overlap.html  : {run_paths.artifact_dir / 'overlap.html'}")
    print(f"reliability venns: {len(overlap['reliability'])}")
    print(f"exploratory venns: {len(overlap['exploratory'])}")
    _print_health(manifest)


@app.command
def diff(*, run: str, judge: str, model: str | None = None) -> None:
    """Compare a judge's rows across prompt versions, within one model."""
    run_paths = RunPaths(Path(run))
    rows = list(read_jsonl(run_paths.judgement_file(judge)))
    if not rows:
        _fail(f"no rows for judge {judge!r} in {run}", EXIT_USAGE)

    models = sorted({row["model_id"] for row in rows})
    if len(models) > 1 and model is None:
        _fail(
            f"judge {judge!r} was run against {len(models)} models "
            f"({', '.join(models)}); pass --model to name one. Diffing across models "
            "would confound a prompt change with a model change.",
            EXIT_USAGE,
        )
    chosen = model or models[0]
    rows = [row for row in rows if row["model_id"] == chosen]

    by_sha: dict[str, list[dict]] = {}
    for row in rows:
        by_sha.setdefault(row["prompt_sha256"], []).append(row)

    print(f"judge {judge} · model {chosen} · {len(by_sha)} prompt version(s)")
    shas = sorted(by_sha, key=lambda s: min(r["timestamp_utc"] for r in by_sha[s]))
    for sha in shas:
        group = by_sha[sha]
        ok = sum(1 for r in group if r["parse_ok"])
        print(f"  {sha[:12]}: {len(group)} rows · {ok} parsed · {len(group) - ok} failed")

    if len(shas) >= 2:
        old, new = shas[-2], shas[-1]
        old_by_sample = {r["sample_key"]: r for r in by_sha[old] if r["parse_ok"]}
        new_by_sample = {r["sample_key"]: r for r in by_sha[new] if r["parse_ok"]}
        shared = sorted(set(old_by_sample) & set(new_by_sample))
        changed = []
        for key in shared:
            before = {f["field"]: f["value"] for f in old_by_sample[key]["parsed"]["findings"]}
            after = {f["field"]: f["value"] for f in new_by_sample[key]["parsed"]["findings"]}
            if before != after:
                changed.append((key, before, after))
        print(f"\n{old[:12]} -> {new[:12]}: {len(changed)}/{len(shared)} shared samples changed")
        for key, before, after in changed[:20]:
            flips = [
                f"{k}: {before.get(k)} -> {after.get(k)}"
                for k in sorted(set(before) | set(after))
                if before.get(k) != after.get(k)
            ]
            print(f"  {key}: {'; '.join(flips)}")


@app.command
def manifest(*, run: str) -> None:
    """Print the run manifest."""
    data = read_json(RunPaths(Path(run)).manifest)
    print(json.dumps(data, indent=2, sort_keys=True))
    _print_health(data)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
