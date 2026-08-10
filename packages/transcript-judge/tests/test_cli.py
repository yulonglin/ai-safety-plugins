"""The `tj` command surface: exit codes, refusals, and what gets printed.

Commands are driven through the cyclopts app with real argv tokens, so a
renamed flag breaks these tests. Nothing here reaches the network: the one
place the CLI would build a real client is patched to a fake.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from conftest import FakeClient, finding

from transcript_judge import cli
from transcript_judge.persist import read_json

FIXTURES = Path(__file__).parent / "fixtures"
ALPHA = str(FIXTURES / "judge_alpha.v1.md")

SAMPLES = [
    {
        "sample_key": "protocolqa:a1:1",
        "messages": [
            {"role": "user", "content": "Step 1: Add 300 µL cold TRIzol – then vortex."},
            {"role": "assistant", "content": "The 300 µL volume looks wrong for 10⁷ cells."},
        ],
        "metadata": {"ideal": "one millilitre of TRIzol per ten million cells", "subtask": "rna"},
    },
    {
        "sample_key": "protocolqa:a2:1",
        "messages": [
            {"role": "user", "content": "Step 2: Incubate at 65 °C for 10 minutes."},
            {"role": "assistant", "content": "That looks right to me."},
        ],
        "metadata": {"ideal": "sixty-five degrees Celsius is correct", "subtask": "rna"},
    },
    {
        "sample_key": "protocolqa:a3:1",
        "messages": [
            {"role": "user", "content": "Step 3: Spin at 12000 × g for 15 min."},
            {"role": "assistant", "content": "The 12000 × g figure is too low here."},
        ],
        "metadata": {"ideal": "spin considerably faster than that", "subtask": "dna"},
    },
]


def tj(*tokens: str) -> int:
    """Run one `tj` invocation and return its exit code.

    cyclopts calls `sys.exit` on every path, success included, so the exit code
    is the only thing worth asserting on -- and asserting on it is exactly what
    a caller in a shell script would depend on.
    """
    with pytest.raises(SystemExit) as exc:
        cli.app(list(tokens))
    return exc.value.code


@pytest.fixture
def transcripts(tmp_path) -> str:
    path = tmp_path / "transcripts.jsonl"
    path.write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in SAMPLES) + "\n", encoding="utf-8"
    )
    return str(path)


@pytest.fixture
def loaded_run(tmp_path, transcripts) -> str:
    run_dir = str(tmp_path / "run")
    assert tj("load", transcripts, "--run", run_dir) == 0
    return run_dir


def fake_findings(value_by_render_id: dict[str, bool]) -> dict[str, object]:
    return {
        rid: [
            finding(
                "flags_protocol_error",
                value,
                quote="300 µL" if value else None,
                message_index=0,
            ),
            finding("omits_safety_caveat", False),
        ]
        for rid, value in value_by_render_id.items()
    }


ALL_POSITIVE = {"s0001": True, "s0002": True, "s0003": True}


def patch_judges(monkeypatch, client) -> None:
    """Inject a fake client into `tj run` without touching provider code."""
    real = cli.run_judges

    async def patched(**kwargs):
        kwargs["client_factory"] = lambda provider: client
        return await real(**kwargs)

    monkeypatch.setattr(cli, "run_judges", patched)


# --- load --------------------------------------------------------------------


def test_load_writes_transcripts_and_a_manifest(loaded_run):
    paths = cli.RunPaths(Path(loaded_run))

    assert paths.transcripts.exists()
    manifest = read_json(paths.manifest)
    assert manifest["n_samples"] == 3
    assert manifest["n_messages"] == 6
    assert manifest["blinded"] is True
    assert len(manifest["transcripts_sha256"]) == 64


def test_load_reports_the_corpus_it_ingested(tmp_path, transcripts, capsys):
    assert tj("load", transcripts, "--run", str(tmp_path / "run")) == 0

    out = capsys.readouterr().out
    assert "samples: 3 · messages: 6" in out
    assert "non-text blocks elided: 0" in out


def test_load_assigns_opaque_render_ids_in_sorted_key_order(loaded_run):
    manifest = read_json(cli.RunPaths(Path(loaded_run)).manifest)

    assert manifest["sample_id_map"] == {
        "protocolqa:a1:1": "s0001",
        "protocolqa:a2:1": "s0002",
        "protocolqa:a3:1": "s0003",
    }


def test_load_records_the_input_hash_so_a_changed_corpus_is_detectable(loaded_run, transcripts):
    manifest = read_json(cli.RunPaths(Path(loaded_run)).manifest)

    assert list(manifest["input_data_sha256"]) == [transcripts]
    assert len(manifest["input_data_sha256"][transcripts]) == 64


def test_load_refuses_an_empty_corpus(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")

    assert tj("load", str(empty), "--run", str(tmp_path / "run")) == cli.EXIT_USAGE


# --- run --dry-run -----------------------------------------------------------


def test_dry_run_prints_the_resolved_cell_and_makes_no_network_call(loaded_run, capsys):
    assert tj("run", "--run", loaded_run, "--judge", ALPHA, "--dry-run") == 0

    out = capsys.readouterr().out
    assert "dry run: 1 judge cell(s), no network calls" in out
    assert "provider : anthropic" in out
    assert "model    : claude-sonnet-5" in out
    assert "surface  : full" in out
    assert "flags_protocol_error(positive_quote)" in out
    assert "omits_safety_caveat(hand_validation)" in out


def test_dry_run_prints_one_block_per_model(loaded_run, capsys):
    assert (
        tj(
            "run",
            "--run",
            loaded_run,
            "--judge",
            ALPHA,
            "--dry-run",
            "--model",
            "anthropic:claude-sonnet-5",
            "--model",
            "openrouter:openai/gpt-5.6-sol",
        )
        == 0
    )

    out = capsys.readouterr().out
    assert "dry run: 2 judge cell(s)" in out
    assert "model    : claude-sonnet-5" in out
    assert "model    : openai/gpt-5.6-sol" in out


def test_dry_run_leaves_no_judgement_rows(loaded_run):
    tj("run", "--run", loaded_run, "--judge", ALPHA, "--dry-run")

    assert not cli.RunPaths(Path(loaded_run)).judgement_file("alpha").exists()


# --- blinding refusals -------------------------------------------------------


@pytest.mark.parametrize("key", ["ideal", "distractors", "grading", "scores", "target"])
def test_a_denylisted_metadata_key_exits_non_zero(loaded_run, key, capsys):
    code = tj("run", "--run", loaded_run, "--judge", ALPHA, "--dry-run", "--include-metadata", key)

    assert code == cli.EXIT_BLINDING
    err = capsys.readouterr().err
    assert key in err
    assert "cannot be overridden" in err


def test_an_allowed_metadata_key_is_accepted(loaded_run, capsys):
    code = tj(
        "run", "--run", loaded_run, "--judge", ALPHA, "--dry-run", "--include-metadata", "subtask"
    )

    assert code == 0
    assert "dry run" in capsys.readouterr().out


def test_a_bad_evidence_mode_exits_with_the_schema_code(loaded_run, capsys):
    code = tj(
        "run",
        "--run",
        loaded_run,
        "--judge",
        str(FIXTURES / "judge_bad_mode.v1.md"),
        "--dry-run",
    )

    assert code == cli.EXIT_SCHEMA
    assert "vibes" in capsys.readouterr().err


def test_a_missing_evidence_mode_exits_with_the_schema_code(loaded_run, capsys):
    code = tj(
        "run",
        "--run",
        loaded_run,
        "--judge",
        str(FIXTURES / "judge_missing_mode.v1.md"),
        "--dry-run",
    )

    assert code == cli.EXIT_SCHEMA
    assert "never inferred from the field name" in capsys.readouterr().err


def test_an_unsupported_param_exits_before_the_dry_run_prints_it(loaded_run, capsys):
    """Fail closed, and fail early.

    Prompt frontmatter takes any mapping and the manifest records it verbatim,
    but the providers forward only `max_tokens` and `temperature`. A `top_p` that
    reaches the dry-run listing and the manifest while no request ever carries it
    describes a sampling regime that did not happen.
    """
    code = tj(
        "run",
        "--run",
        loaded_run,
        "--judge",
        str(FIXTURES / "judge_unknown_param.v1.md"),
        "--dry-run",
    )
    captured = capsys.readouterr()

    assert code == cli.EXIT_PARAMS
    assert "top_p" in captured.err
    assert "not supported by provider 'anthropic'" in captured.err
    # The refusal precedes the listing; otherwise the falsehood is printed anyway.
    assert "dry run" not in captured.out


def test_a_supported_param_still_reaches_the_dry_run(loaded_run, capsys):
    """The gate must admit the legal case -- a blanket refusal would also pass above."""
    code = tj("run", "--run", loaded_run, "--judge", ALPHA, "--dry-run")

    assert code == 0
    assert "dry run" in capsys.readouterr().out


def test_run_without_a_loaded_manifest_is_a_usage_error(tmp_path):
    assert tj("run", "--run", str(tmp_path / "nothing"), "--judge", ALPHA) == cli.EXIT_USAGE


# --- run ---------------------------------------------------------------------


def test_run_persists_a_row_per_sample_and_reports_the_cell(loaded_run, monkeypatch, capsys):
    client = FakeClient("anthropic", fake_findings({"s0001": True, "s0002": False, "s0003": True}))
    patch_judges(monkeypatch, client)

    assert tj("run", "--run", loaded_run, "--judge", ALPHA) == 0

    out = capsys.readouterr().out
    assert "3 ok · 0 parse failures · 0 skipped" in out
    assert "health: parse failures 0" in out

    manifest = read_json(cli.RunPaths(Path(loaded_run)).manifest)
    (cell,) = manifest["judge_cells"]
    assert cell["judge_name"] == "alpha"
    assert cell["model_id"] == "claude-sonnet-5"
    assert cell["rows_parse_ok"] == 3
    assert cell["fields"] == [
        {"name": "flags_protocol_error", "evidence_mode": "positive_quote"},
        {"name": "omits_safety_caveat", "evidence_mode": "hand_validation"},
    ]


def test_run_never_sends_the_reference_answer_or_the_sample_key(loaded_run, monkeypatch):
    client = FakeClient("anthropic", fake_findings(ALL_POSITIVE))
    patch_judges(monkeypatch, client)

    tj("run", "--run", loaded_run, "--judge", ALPHA)

    assert len(client.calls) == 3
    for call in client.calls:
        assert "one millilitre of TRIzol per ten million cells" not in call["user"]
        assert "sixty-five degrees Celsius is correct" not in call["user"]
        assert "spin considerably faster than that" not in call["user"]
        assert "protocolqa:" not in call["user"]
        assert "ideal" not in call["user"]


def test_limit_bounds_the_number_of_samples_judged(loaded_run, monkeypatch, capsys):
    client = FakeClient("anthropic", fake_findings(ALL_POSITIVE))
    patch_judges(monkeypatch, client)

    tj("run", "--run", loaded_run, "--judge", ALPHA, "--limit", "2")

    assert len(client.calls) == 2
    assert "2 ok" in capsys.readouterr().out


def test_limit_selects_by_sorted_sample_key_not_file_order(tmp_path, monkeypatch, capsys):
    """The transcripts land in reverse order, so file order and sorted order disagree.
    `--limit 2` must judge a1 and a2 -- the first two by `sample_key` -- never a3."""
    path = tmp_path / "reversed.jsonl"
    path.write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in reversed(SAMPLES)) + "\n",
        encoding="utf-8",
    )
    run_dir = str(tmp_path / "run")
    assert tj("load", str(path), "--run", run_dir) == 0

    client = FakeClient("anthropic", fake_findings(ALL_POSITIVE))
    patch_judges(monkeypatch, client)
    tj("run", "--run", run_dir, "--judge", ALPHA, "--limit", "2")

    manifest = read_json(cli.RunPaths(Path(run_dir)).manifest)
    assert manifest["judged_sample_keys"] == ["protocolqa:a1:1", "protocolqa:a2:1"]
    assert manifest["limit"] == 2
    # The third sample's text must never have reached the model.
    assert len(client.calls) == 2
    for call in client.calls:
        assert "12000" not in call["user"]


def test_a_rerun_skips_rows_that_already_parsed(loaded_run, monkeypatch, capsys):
    script = fake_findings({"s0001": True, "s0002": False, "s0003": True})
    patch_judges(monkeypatch, FakeClient("anthropic", script))
    tj("run", "--run", loaded_run, "--judge", ALPHA)
    capsys.readouterr()

    second = FakeClient("anthropic", script)
    patch_judges(monkeypatch, second)
    tj("run", "--run", loaded_run, "--judge", ALPHA)

    assert second.calls == []
    assert "0 ok · 0 parse failures · 3 skipped" in capsys.readouterr().out


def test_parse_failures_are_reported_as_a_count_not_swallowed(loaded_run, monkeypatch, capsys):
    script = fake_findings({"s0002": True, "s0003": True})
    script["s0001"] = "malformed"
    patch_judges(monkeypatch, FakeClient("anthropic", script))

    tj("run", "--run", loaded_run, "--judge", ALPHA)

    out = capsys.readouterr().out
    assert "2 ok · 1 parse failures" in out
    assert "health: parse failures 1" in out


# --- stats refuses on an unblinded run ---------------------------------------


def test_stats_refuses_to_print_agreement_for_an_unblinded_run(loaded_run, capsys):
    paths = cli.RunPaths(Path(loaded_run))
    manifest = read_json(paths.manifest)
    manifest["blinded"] = False
    cli.write_json(paths.manifest, manifest)

    assert tj("stats", "--run", loaded_run) == cli.EXIT_BLINDING
    assert "Refusing" in capsys.readouterr().err


# --- stats covers every model pair -------------------------------------------

PAIR_LINE = re.compile(r"^flags_error \[(?P<a>[^ ]+) vs (?P<b>[^\]]+)\]: ")
PAIRED_LINE = re.compile(r"^  paired samples (?P<n>\d+) ")


def write_labels(run: str, coverage: dict[str, list[str]]) -> None:
    """Write one `flags_error` label per (model, sample) in `coverage`."""
    path = cli.RunPaths(Path(run)).labels
    rows = [
        {
            "label_id": f"{model}:{sample}",
            "sample_key": sample,
            "label": "flags_error",
            "evidence_mode": "positive_quote",
            "value": True,
            "judge_name": "alpha",
            "prompt_sha256": "a" * 64,
            "model_id": model,
            "surface": "full",
            "judgement_row_id": f"alpha.jsonl:{i}",
        }
        for i, (model, samples) in enumerate(sorted(coverage.items()))
        for sample in samples
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def stats_pairs(capsys) -> tuple[list[tuple[str, str]], dict[tuple[str, str], int]]:
    """The (model_a, model_b) rows `tj stats` printed, and each row's n_paired."""
    lines = capsys.readouterr().out.splitlines()
    pairs: list[tuple[str, str]] = []
    paired: dict[tuple[str, str], int] = {}
    for i, line in enumerate(lines):
        match = PAIR_LINE.match(line)
        if not match:
            continue
        pair = (match["a"], match["b"])
        pairs.append(pair)
        n = PAIRED_LINE.match(lines[i + 1])
        assert n is not None, f"no paired-samples line after {line!r}"
        paired[pair] = int(n["n"])
    return pairs, paired


def test_stats_compares_every_unordered_model_pair_not_just_the_first_two(loaded_run, capsys):
    write_labels(
        loaded_run,
        {
            "model-a": ["s0001", "s0002", "s0003"],
            "model-b": ["s0001", "s0002", "s0003"],
            "model-c": ["s0001"],
        },
    )

    assert tj("stats", "--run", loaded_run, "--permutations", "10") == 0

    pairs, paired = stats_pairs(capsys)
    assert pairs == [("model-a", "model-b"), ("model-a", "model-c"), ("model-b", "model-c")]
    assert paired[("model-a", "model-c")] == 1
    assert paired[("model-b", "model-c")] == 1


def test_a_third_model_does_not_shrink_an_existing_pairs_denominator(loaded_run, capsys):
    two = {"model-a": ["s0001", "s0002", "s0003"], "model-b": ["s0001", "s0002", "s0003"]}
    write_labels(loaded_run, two)
    assert tj("stats", "--run", loaded_run, "--permutations", "10") == 0
    _, paired_without_c = stats_pairs(capsys)

    write_labels(loaded_run, {**two, "model-c": ["s0001"]})
    assert tj("stats", "--run", loaded_run, "--permutations", "10") == 0
    _, paired_with_c = stats_pairs(capsys)

    assert paired_without_c[("model-a", "model-b")] == 3
    assert paired_with_c[("model-a", "model-b")] == 3


# --- diff --------------------------------------------------------------------


def two_model_run(loaded_run, monkeypatch, capsys) -> None:
    patch_judges(monkeypatch, FakeClient("anthropic", fake_findings(ALL_POSITIVE)))
    tj(
        "run",
        "--run",
        loaded_run,
        "--judge",
        ALPHA,
        "--model",
        "anthropic:claude-sonnet-5",
        "--model",
        "openrouter:openai/gpt-5.6-sol",
    )
    capsys.readouterr()


def test_diff_refuses_to_confound_a_prompt_change_with_a_model_change(
    loaded_run, monkeypatch, capsys
):
    two_model_run(loaded_run, monkeypatch, capsys)

    assert tj("diff", "--run", loaded_run, "--judge", "alpha") == cli.EXIT_USAGE
    assert "would confound a prompt change with a model change" in capsys.readouterr().err


def test_diff_within_one_model_reports_the_prompt_versions(loaded_run, monkeypatch, capsys):
    two_model_run(loaded_run, monkeypatch, capsys)

    assert tj("diff", "--run", loaded_run, "--judge", "alpha", "--model", "claude-sonnet-5") == 0

    out = capsys.readouterr().out
    assert "judge alpha · model claude-sonnet-5 · 1 prompt version(s)" in out
    assert "3 rows · 3 parsed · 0 failed" in out


def test_diff_on_an_unjudged_judge_is_a_usage_error(loaded_run):
    assert tj("diff", "--run", loaded_run, "--judge", "alpha") == cli.EXIT_USAGE


# --- manifest ----------------------------------------------------------------


def test_manifest_prints_json_and_the_health_line(loaded_run, capsys):
    assert tj("manifest", "--run", loaded_run) == 0

    out = capsys.readouterr().out
    body, _, health = out.partition("\nhealth:")
    assert json.loads(body)["n_samples"] == 3
    assert "blinded True" in health
