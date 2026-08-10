"""Append-only JSONL, byte-offset row ids, and cell-keyed resume."""

from __future__ import annotations

import json

from transcript_judge.models import JudgeCell
from transcript_judge.persist import (
    RunPaths,
    append_jsonl,
    cells_in_file,
    judgements_sha256,
    load_completed,
    read_json,
    read_jsonl,
    read_row_at,
    row_id,
    split_row_id,
    transcripts_sha256,
    utc_now,
    write_json,
)

PROMPT_A = "a" * 64
PROMPT_B = "b" * 64


def judgement(
    sample_key: str, *, model_id: str, prompt_sha256: str = PROMPT_A, parse_ok: bool = True
) -> dict:
    return {
        "sample_key": sample_key,
        "judge_name": "alpha",
        "prompt_sha256": prompt_sha256,
        "model_id": model_id,
        "provider": "anthropic",
        "surface": "full",
        "rendered_input": "sample: s0001\n",
        "raw_output": "{}",
        "parse_ok": parse_ok,
    }


# --- layout ------------------------------------------------------------------


def test_run_paths_derive_every_artefact_from_the_root(tmp_path):
    paths = RunPaths(root=tmp_path / "run")
    assert paths.manifest == tmp_path / "run" / "manifest.json"
    assert paths.transcripts == tmp_path / "run" / "transcripts.jsonl"
    assert paths.labels == tmp_path / "run" / "labels.jsonl"
    assert paths.report == tmp_path / "run" / "report.md"
    assert paths.judgement_file("alpha") == tmp_path / "run" / "judgements" / "alpha.jsonl"


def test_ensure_creates_the_directories_and_is_idempotent(tmp_path):
    paths = RunPaths(root=tmp_path / "run").ensure().ensure()
    assert paths.judgements_dir.is_dir()
    assert paths.clusters_dir.is_dir()
    assert paths.artifact_dir.is_dir()


def test_one_file_per_prompt_holds_every_cell_of_that_prompt(tmp_path):
    paths = RunPaths(root=tmp_path / "run").ensure()
    append_jsonl(paths.judgement_file("alpha"), judgement("s1", model_id="claude-sonnet-5"))
    append_jsonl(paths.judgement_file("alpha"), judgement("s1", model_id="openai/gpt-5.6-sol"))
    assert sorted(p.name for p in paths.judgements_dir.iterdir()) == ["alpha.jsonl"]
    assert len(list(read_jsonl(paths.judgement_file("alpha")))) == 2


# --- append-only, with offsets ----------------------------------------------


def test_appending_returns_an_offset_that_seeks_straight_to_the_row(tmp_path):
    path = tmp_path / "alpha.jsonl"
    first = append_jsonl(path, {"n": 1})
    second = append_jsonl(path, {"n": 2})
    third = append_jsonl(path, {"n": 3})
    assert first == 0
    assert second > first
    assert read_row_at(path, second) == {"n": 2}
    assert read_row_at(path, third) == {"n": 3}


def test_an_earlier_row_is_byte_identical_after_a_later_append(tmp_path):
    path = tmp_path / "alpha.jsonl"
    append_jsonl(path, {"n": 1, "text": "300 µL"})
    before = path.read_bytes()
    append_jsonl(path, {"n": 2})
    assert path.read_bytes().startswith(before)


def test_offsets_survive_non_ascii_content(tmp_path):
    path = tmp_path / "alpha.jsonl"
    append_jsonl(path, {"text": "300 µL – TRIzol"})
    offset = append_jsonl(path, {"text": "second"})
    assert read_row_at(path, offset) == {"text": "second"}


def test_reading_a_missing_file_yields_nothing(tmp_path):
    assert list(read_jsonl(tmp_path / "absent.jsonl")) == []


def test_row_ids_round_trip():
    value = row_id("alpha", 4096)
    assert value == "alpha.jsonl:4096"
    assert split_row_id(value) == ("alpha.jsonl", 4096)


# --- resume keys on the cell, not the judge name -----------------------------


def test_completed_work_is_keyed_on_sample_prompt_and_model(tmp_path):
    path = tmp_path / "alpha.jsonl"
    append_jsonl(path, judgement("s1", model_id="claude-sonnet-5"))
    assert load_completed(path) == {("s1", PROMPT_A, "claude-sonnet-5")}


def test_a_second_model_behind_one_prompt_is_not_treated_as_done(tmp_path):
    # Keying on judge_name alone would skip the second model and silently
    # halve the run.
    path = tmp_path / "alpha.jsonl"
    append_jsonl(path, judgement("s1", model_id="claude-sonnet-5"))
    done = load_completed(path)
    assert ("s1", PROMPT_A, "openai/gpt-5.6-sol") not in done


def test_a_reworded_prompt_is_not_treated_as_done(tmp_path):
    path = tmp_path / "alpha.jsonl"
    append_jsonl(path, judgement("s1", model_id="claude-sonnet-5", prompt_sha256=PROMPT_A))
    done = load_completed(path)
    assert ("s1", PROMPT_B, "claude-sonnet-5") not in done


def test_a_failed_row_is_not_treated_as_done(tmp_path):
    path = tmp_path / "alpha.jsonl"
    append_jsonl(path, judgement("s1", model_id="claude-sonnet-5", parse_ok=False))
    assert load_completed(path) == set()


def test_cells_in_file_lists_each_cell_once_in_sorted_order(tmp_path):
    path = tmp_path / "alpha.jsonl"
    append_jsonl(path, judgement("s1", model_id="openai/gpt-5.6-sol"))
    append_jsonl(path, judgement("s1", model_id="claude-sonnet-5"))
    append_jsonl(path, judgement("s2", model_id="claude-sonnet-5"))
    assert cells_in_file(path) == [
        JudgeCell(judge_name="alpha", prompt_sha256=PROMPT_A, model_id="claude-sonnet-5"),
        JudgeCell(judge_name="alpha", prompt_sha256=PROMPT_A, model_id="openai/gpt-5.6-sol"),
    ]


# --- content hashes ----------------------------------------------------------


def test_transcript_hash_ignores_key_order():
    a = transcripts_sha256([{"sample_key": "s1", "messages": []}])
    b = transcripts_sha256([{"messages": [], "sample_key": "s1"}])
    assert a == b


def test_transcript_hash_changes_with_content():
    a = transcripts_sha256([{"sample_key": "s1"}])
    b = transcripts_sha256([{"sample_key": "s2"}])
    assert a != b


def test_transcript_hash_is_order_sensitive():
    a = transcripts_sha256([{"k": 1}, {"k": 2}])
    b = transcripts_sha256([{"k": 2}, {"k": 1}])
    assert a != b


def test_judgement_hash_changes_when_a_new_row_lands(tmp_path):
    path = tmp_path / "alpha.jsonl"
    append_jsonl(path, judgement("s1", model_id="claude-sonnet-5"))
    before = judgements_sha256([path])
    append_jsonl(path, judgement("s2", model_id="claude-sonnet-5"))
    assert judgements_sha256([path]) != before


def test_judgement_hash_is_independent_of_the_order_paths_are_given(tmp_path):
    a = tmp_path / "alpha.jsonl"
    b = tmp_path / "beta.jsonl"
    append_jsonl(a, judgement("s1", model_id="claude-sonnet-5"))
    append_jsonl(b, judgement("s1", model_id="claude-sonnet-5"))
    assert judgements_sha256([a, b]) == judgements_sha256([b, a])


# --- json helpers ------------------------------------------------------------


def test_json_round_trips_and_is_written_sorted(tmp_path):
    path = tmp_path / "manifest.json"
    write_json(path, {"b": 1, "a": {"y": 2, "x": 3}})
    assert read_json(path) == {"b": 1, "a": {"y": 2, "x": 3}}
    assert path.read_text(encoding="utf-8").index('"a"') < path.read_text(encoding="utf-8").index(
        '"b"'
    )


def test_json_keeps_non_ascii_readable(tmp_path):
    path = tmp_path / "manifest.json"
    write_json(path, {"t": "300 µL"})
    assert "300 µL" in path.read_text(encoding="utf-8")


def test_timestamps_are_utc_iso_8601_to_the_second():
    stamp = utc_now()
    assert stamp.endswith("Z")
    assert len(stamp) == 20
    json.dumps(stamp)
