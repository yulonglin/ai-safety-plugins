"""Format detection and the non-Inspect loaders.

The `.eval` loader is exercised by a real log in the smoke check rather than
here: it needs `inspect-ai` installed, and a fixture `.eval` would be a
re-implementation of the format rather than a test of it.
"""

from __future__ import annotations

import json

import pytest

from transcript_judge.loaders import FORMATS, detect_format, load


def test_formats_are_pinned():
    assert FORMATS == ("auto", "inspect_eval", "jsonl", "plain")


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("run.eval", "inspect_eval"),
        ("run.EVAL", "inspect_eval"),
        ("t.jsonl", "jsonl"),
        ("t.ndjson", "jsonl"),
        ("t.json", "plain"),
        ("t.txt", "plain"),
    ],
)
def test_detect_format(tmp_path, filename: str, expected: str):
    assert detect_format(tmp_path / filename) == expected


def test_unknown_format_is_refused(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown format 'xml'"):
        load(path, format="xml")


def test_a_missing_path_is_refused(tmp_path):
    with pytest.raises(FileNotFoundError, match="no such transcript path"):
        load(tmp_path / "absent.jsonl")


def _write_jsonl(path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_jsonl_loads_one_sample_per_line_with_indexed_messages(tmp_path):
    path = tmp_path / "run.jsonl"
    _write_jsonl(
        path,
        [
            {
                "id": "a1",
                "epoch": 1,
                "messages": [
                    {"role": "user", "content": "question"},
                    {"role": "assistant", "content": "answer"},
                ],
            }
        ],
    )
    (sample,) = load(path)
    assert sample.sample_key == "run:a1:1"
    assert [m.index for m in sample.messages] == [0, 1]
    assert [m.role for m in sample.messages] == ["user", "assistant"]
    assert [m.text for m in sample.messages] == ["question", "answer"]


def test_jsonl_sample_key_falls_back_to_the_line_number(tmp_path):
    path = tmp_path / "run.jsonl"
    _write_jsonl(path, [{"messages": []}, {"messages": []}])
    keys = [s.sample_key for s in load(path)]
    assert keys == ["run:0:1", "run:1:1"]


def test_an_explicit_sample_key_wins(tmp_path):
    path = tmp_path / "run.jsonl"
    _write_jsonl(path, [{"sample_key": "given:key:3", "id": "ignored", "messages": []}])
    assert load(path)[0].sample_key == "given:key:3"


def test_blank_lines_are_skipped(tmp_path):
    path = tmp_path / "run.jsonl"
    path.write_text('{"id":"a","messages":[]}\n\n{"id":"b","messages":[]}\n', encoding="utf-8")
    assert len(load(path)) == 2


def test_everything_but_messages_lands_in_extra(tmp_path):
    path = tmp_path / "run.jsonl"
    _write_jsonl(path, [{"id": "a", "metadata": {"subtask": "rna"}, "messages": []}])
    sample = load(path)[0]
    assert sample.extra["metadata"] == {"subtask": "rna"}
    assert "messages" not in sample.extra


def test_block_content_and_phase_survive_the_loader(tmp_path):
    path = tmp_path / "run.jsonl"
    _write_jsonl(
        path,
        [
            {
                "id": "a",
                "messages": [
                    {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "first"},
                            {"type": "image", "source": {}},
                        ],
                        "internal": {"message_phase": "final_answer"},
                    }
                ],
            }
        ],
    )
    stats: dict[str, int] = {}
    (sample,) = load(path, stats=stats)
    assert sample.messages[0].text == "first\n\n[non-text block: image]"
    assert sample.messages[0].phase == "final_answer"
    assert stats["non_text_blocks_elided"] == 1


def test_a_json_document_loads_as_one_sample(tmp_path):
    path = tmp_path / "one.json"
    path.write_text(
        json.dumps({"id": "z", "messages": [{"role": "user", "content": "hi"}]}), encoding="utf-8"
    )
    (sample,) = load(path)
    assert sample.sample_key == "one:z:1"
    assert sample.messages[0].text == "hi"


def test_a_json_list_loads_as_several_samples(tmp_path):
    path = tmp_path / "many.json"
    path.write_text(
        json.dumps([{"id": "a", "messages": []}, {"id": "b", "messages": []}]), encoding="utf-8"
    )
    assert [s.sample_key for s in load(path)] == ["many:a:1", "many:b:1"]


def test_a_text_file_becomes_a_single_user_message(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("raw transcript body", encoding="utf-8")
    (sample,) = load(path)
    assert sample.sample_key == "note:0:1"
    assert sample.messages[0].role == "user"
    assert sample.messages[0].text == "raw transcript body"


def test_a_directory_loads_its_children_in_sorted_order(tmp_path):
    _write_jsonl(tmp_path / "b.jsonl", [{"id": "1", "messages": []}])
    _write_jsonl(tmp_path / "a.jsonl", [{"id": "1", "messages": []}])
    (tmp_path / "ignored.png").write_bytes(b"\x89PNG")
    assert [s.sample_key for s in load(tmp_path)] == ["a:1:1", "b:1:1"]
