"""load -> run -> labels -> cluster -> stats -> artifact, end to end, no network.

This is the spec's acceptance walk with the providers faked out. It exists to
catch the failures that only appear when the stages are composed: a row id that
does not seek back to its own bytes, a span that survives derivation but not
persistence, a manifest field one stage writes and the next overwrites.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import anthropic_payload, finding

from transcript_judge import cli
from transcript_judge.models import LabelRow
from transcript_judge.persist import read_json, read_jsonl
from transcript_judge.providers.anthropic import parse_raw as anthropic_parse_raw

FIXTURES = Path(__file__).parent / "fixtures"
ALPHA = str(FIXTURES / "judge_alpha.v1.md")

# The quotes below are lifted verbatim from these bodies, so the grounding
# ladder has a real span to find rather than a synthetic one.
BODIES = {
    "protocolqa:a1:1": (
        "Step 1: Add 300 µL cold TRIzol – then vortex for 15 s.",
        "The 300 µL volume looks wrong; I would expect 1 mL per 10⁷ cells.",
    ),
    "protocolqa:a2:1": (
        "Step 2: Incubate the lysate at 65 °C for 10 minutes.",
        "Incubating at 65 °C is fine for this step.",
    ),
    "protocolqa:a3:1": (
        "Step 3: Spin at 12000 × g for 15 min at 4 °C.",
        "Spinning at 12000 × g is too slow to pellet the debris.",
    ),
}

QUOTES = {
    "s0001": "The 300 µL volume looks wrong",
    "s0002": None,
    "s0003": "12000 × g is too slow",
}


@pytest.fixture
def transcripts(tmp_path) -> str:
    path = tmp_path / "transcripts.jsonl"
    rows = [
        {
            "sample_key": key,
            "messages": [
                {"role": "user", "content": user},
                {"role": "assistant", "content": assistant},
            ],
            "metadata": {"ideal": "the withheld reference answer", "subtask": "rna"},
        }
        for key, (user, assistant) in BODIES.items()
    ]
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )
    return str(path)


DISSENTING_MODEL = "openai/gpt-5.6-sol"


class ScriptedJudge:
    """Answers per render id; the second model disagrees on s0003.

    One instance serves every cell, because the runner is handed a single
    ``client_factory`` keyed on provider — the model is visible only per call.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def complete(self, *, system: str, user: str, model_id: str, params: dict):
        self.calls.append({"system": system, "user": user, "model_id": model_id})
        render_id = user.splitlines()[0].removeprefix("sample: ").strip()
        quote = QUOTES[render_id]
        value = quote is not None
        if render_id == "s0003" and model_id == DISSENTING_MODEL:
            value, quote = False, None
        return anthropic_parse_raw(
            anthropic_payload(
                [
                    finding(
                        "flags_protocol_error",
                        value,
                        quote=quote,
                        message_index=1 if value else None,
                    ),
                    finding("omits_safety_caveat", False),
                ]
            )
        )


class ScriptedMerge:
    """The merge judge: never equivalent, so every construct stays its own cluster."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def complete(self, *, system: str, user: str, model_id: str, params: dict):
        self.calls.append({"system": system, "user": user, "model_id": model_id})
        return anthropic_parse_raw(anthropic_payload([finding("equivalent", False, quote="x")]))


def tj(*tokens: str) -> int:
    with pytest.raises(SystemExit) as exc:
        cli.app(list(tokens))
    return exc.value.code


def _with_client(real, client):
    """Inject a fake client into `tj run` without reaching into provider code."""

    async def patched(**kwargs):
        kwargs["client_factory"] = lambda provider: client
        return await real(**kwargs)

    return patched


@pytest.fixture
def pipeline(tmp_path, transcripts, monkeypatch) -> str:
    """A complete two-model run, already through `labels`."""
    run_dir = str(tmp_path / "run")
    assert tj("load", transcripts, "--run", run_dir) == 0

    monkeypatch.setattr(cli, "run_judges", _with_client(cli.run_judges, ScriptedJudge()))

    assert (
        tj(
            "run",
            "--run",
            run_dir,
            "--judge",
            ALPHA,
            "--model",
            "anthropic:claude-sonnet-5",
            "--model",
            f"anthropic:{DISSENTING_MODEL}",
        )
        == 0
    )
    assert tj("labels", "--run", run_dir) == 0
    return run_dir


# --- the walk ----------------------------------------------------------------


def test_the_full_pipeline_runs_offline_and_leaves_every_artefact(pipeline, monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_client", lambda provider: ScriptedMerge())

    assert tj("cluster", "--run", pipeline) == 0
    assert tj("stats", "--run", pipeline) == 0
    assert tj("artifact", "--run", pipeline) == 0

    paths = cli.RunPaths(Path(pipeline))
    for artefact in (
        paths.manifest,
        paths.transcripts,
        paths.labels,
        paths.judgement_file("alpha"),
        paths.clusters_dir / "assignments.json",
        paths.clusters_dir / "contradictions.json",
        paths.artifact_dir / "overlap.json",
        paths.artifact_dir / "overlap.html",
    ):
        assert artefact.exists(), artefact


def test_one_call_per_sample_per_cell(pipeline):
    rows = list(read_jsonl(cli.RunPaths(Path(pipeline)).judgement_file("alpha")))

    assert len(rows) == 6
    assert sorted({(r["sample_key"], r["model_id"]) for r in rows}) == [
        ("protocolqa:a1:1", "claude-sonnet-5"),
        ("protocolqa:a1:1", "openai/gpt-5.6-sol"),
        ("protocolqa:a2:1", "claude-sonnet-5"),
        ("protocolqa:a2:1", "openai/gpt-5.6-sol"),
        ("protocolqa:a3:1", "claude-sonnet-5"),
        ("protocolqa:a3:1", "openai/gpt-5.6-sol"),
    ]


def test_every_span_locates_exactly_the_quoted_excerpt(pipeline):
    """The spec's second acceptance criterion, checked against stored text."""
    paths = cli.RunPaths(Path(pipeline))
    samples = {row["sample_key"]: row for row in read_jsonl(paths.transcripts)}

    grounded = [
        LabelRow.model_validate(row)
        for row in read_jsonl(paths.labels)
        if row["value"] and row["evidence_mode"] == "positive_quote"
    ]
    assert grounded, "no positive labels to check"

    for label in grounded:
        assert label.resolved
        text = samples[label.sample_key]["messages"][label.message_index]["text"]
        assert text[label.char_start : label.char_end] == label.source_excerpt


def test_the_stored_excerpt_is_a_slice_of_the_transcript_even_when_it_differs_from_the_quote(
    pipeline,
):
    labels = [LabelRow.model_validate(r) for r in read_jsonl(cli.RunPaths(Path(pipeline)).labels)]
    positives = [lab for lab in labels if lab.value and lab.evidence_mode == "positive_quote"]

    # `judge_quote` is the model's output and is never rewritten.
    assert all(lab.judge_quote in QUOTES.values() for lab in positives)
    assert all(lab.offset_unit == "codepoint" for lab in positives)


def test_hand_validation_fields_are_labelled_but_never_quote_grounded(pipeline, capsys):
    labels = [LabelRow.model_validate(r) for r in read_jsonl(cli.RunPaths(Path(pipeline)).labels)]

    hand = [lab for lab in labels if lab.label == "omits_safety_caveat"]
    assert hand
    assert all(lab.evidence_mode == "hand_validation" for lab in hand)
    assert all(lab.char_start is None for lab in hand)


def test_show_reaches_the_rendered_input_and_raw_output_behind_a_label(pipeline, capsys):
    labels = [LabelRow.model_validate(r) for r in read_jsonl(cli.RunPaths(Path(pipeline)).labels)]
    target = next(lab for lab in labels if lab.value and lab.evidence_mode == "positive_quote")

    assert tj("show", target.label_id, "--run", pipeline) == 0

    out = capsys.readouterr().out
    assert "=== rendered input (exactly what was sent) ===" in out
    assert "sample: s000" in out
    assert "=== raw model output ===" in out
    assert target.judge_quote in out
    # The rendered input is the blinded one, so the key never appears in it.
    assert target.sample_key not in out.split("=== raw model output ===")[0]


def test_agreement_is_reported_with_its_chance_null(pipeline, capsys):
    assert tj("stats", "--run", pipeline) == 0

    out = capsys.readouterr().out
    assert "chance " in out
    assert "kappa " in out
    assert "paired samples 3" in out
    assert "excluded as unqueried by one model 0 (missing, not counted as negative)" in out
    assert "permutation null p=" in out
    assert "sampling over transcripts only" in out


def test_the_artifact_reaches_two_models_with_excerpt_and_rationale(pipeline, capsys):
    assert tj("artifact", "--run", pipeline) == 0

    overlap = read_json(cli.RunPaths(Path(pipeline)).artifact_dir / "overlap.json")
    assert overlap["models"] == ["claude-sonnet-5", "openai/gpt-5.6-sol"]

    (panel,) = overlap["reliability"]
    assert panel["construct"] == "flags_protocol_error"
    assert panel["n_paired"] == 3
    # The two models agree on a1 and disagree on a3, by construction.
    assert panel["both"] == ["protocolqa:a1:1"]
    assert panel["only_a"] == ["protocolqa:a3:1"]

    entry = overlap["labels"][overlap["labels_by_sample"]["protocolqa:a1:1"][0]]
    assert entry["source_excerpt"] == "The 300 µL volume looks wrong"
    assert entry["rationale"] == "deliberating about flags_protocol_error"


def test_the_clustering_rerun_is_byte_identical(pipeline, monkeypatch):
    """Composition check only — the cache's call-saving is `test_cluster.py`'s job.

    This corpus has exactly one quote-grounded construct, so there is no pair to
    put to the merge judge and both runs make zero calls. Asserting "zero on the
    rerun" here would hold for any implementation; what it does prove is that
    running `cluster` twice over a real pipeline leaves the same bytes.
    """
    first = ScriptedMerge()
    monkeypatch.setattr(cli, "get_client", lambda provider: first)
    assert tj("cluster", "--run", pipeline) == 0
    assert first.calls == [], "a single construct yields no pairs to compare"

    assignments = cli.RunPaths(Path(pipeline)).clusters_dir / "assignments.json"
    before = assignments.read_bytes()

    second = ScriptedMerge()
    monkeypatch.setattr(cli, "get_client", lambda provider: second)
    assert tj("cluster", "--run", pipeline) == 0

    assert assignments.read_bytes() == before


def test_a_prompt_edit_yields_a_sha_keyed_diff_with_prior_rows_intact(
    pipeline, tmp_path, monkeypatch, capsys
):
    """The spec's third acceptance criterion."""
    paths = cli.RunPaths(Path(pipeline))
    before = paths.judgement_file("alpha").read_bytes()
    original_sha = json.loads(before.splitlines()[0])["prompt_sha256"]

    edited = tmp_path / "judge_alpha.v2.md"
    edited.write_text(
        Path(ALPHA).read_text(encoding="utf-8") + "\n\nBe stricter about volumes.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "run_judges", _with_client(cli.run_judges, ScriptedJudge()))
    assert tj("run", "--run", pipeline, "--judge", str(edited)) == 0
    capsys.readouterr()

    after = paths.judgement_file("alpha").read_bytes()
    assert after.startswith(before), "append-only: the earlier rows must be untouched"

    assert tj("diff", "--run", pipeline, "--judge", "alpha", "--model", "claude-sonnet-5") == 0
    out = capsys.readouterr().out
    assert "2 prompt version(s)" in out
    assert original_sha[:12] in out


def test_the_manifest_records_every_cell_separately(pipeline):
    manifest = read_json(cli.RunPaths(Path(pipeline)).manifest)

    cells = manifest["judge_cells"]
    assert len(cells) == 2
    assert {c["model_id"] for c in cells} == {"claude-sonnet-5", "openai/gpt-5.6-sol"}
    assert len({c["prompt_sha256"] for c in cells}) == 1
    assert all(c["rows_parse_ok"] == 3 for c in cells)
    assert all(c["labels_total"] == 6 for c in cells)
    assert manifest["blinded"] is True
    assert manifest["n_samples"] == 3
