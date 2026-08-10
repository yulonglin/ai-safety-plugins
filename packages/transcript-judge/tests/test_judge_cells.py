"""The judge cell is the unit of measurement.

``(judge_name, prompt_sha256, model_id)``. Anything that resumes, counts,
compares or de-duplicates keys on all three -- dropping `model_id` would make
two independent measurements look like one repeated one.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from transcript_judge.models import HASH_SEP, JudgeCell, JudgementRow, compute_label_id

CELL = {
    "judge_name": "alpha",
    "prompt_sha256": "a" * 64,
    "model_id": "claude-sonnet-5",
}


def test_a_cell_is_its_three_fields_in_order():
    assert JudgeCell(**CELL).as_tuple() == ("alpha", "a" * 64, "claude-sonnet-5")


def test_a_cell_is_frozen_so_it_can_key_a_dict():
    cell = JudgeCell(**CELL)
    with pytest.raises(ValidationError):
        cell.judge_name = "beta"
    assert {cell: 1}[JudgeCell(**CELL)] == 1


def test_two_models_behind_one_prompt_are_two_cells():
    a = JudgeCell(**CELL)
    b = JudgeCell(**{**CELL, "model_id": "openai/gpt-5.6-sol"})
    assert a != b
    assert len({a, b}) == 2


def test_two_prompt_versions_under_one_name_are_two_cells():
    a = JudgeCell(**CELL)
    b = JudgeCell(**{**CELL, "prompt_sha256": "b" * 64})
    assert a != b
    assert len({a, b}) == 2


def test_the_slug_is_human_facing_and_carries_all_three_parts():
    assert JudgeCell(**CELL).slug == "alpha@aaaaaaaa/claude-sonnet-5"


def test_a_judgement_row_reports_its_own_cell():
    row = JudgementRow(
        sample_key="log:1:1",
        judge_name="alpha",
        prompt_sha256="a" * 64,
        model_id="claude-sonnet-5",
        provider="anthropic",
        surface="full",
        rendered_input="sample: s0001\n",
        raw_output="{}",
    )
    assert row.cell == JudgeCell(**CELL)


# --- label ids ---------------------------------------------------------------

BASE = {
    "sample_key": "log:1:1",
    "judge_name": "alpha",
    "prompt_sha256": "a" * 64,
    "model_id": "claude-sonnet-5",
    "label": "flags_protocol_error",
    "message_index": 1,
    "char_start": 4,
    "char_end": 10,
}


def test_a_label_id_is_sixteen_hex_characters():
    label_id = compute_label_id(**BASE)
    assert len(label_id) == 16
    assert set(label_id) <= set("0123456789abcdef")


def test_the_same_eight_fields_give_the_same_id():
    assert compute_label_id(**BASE) == compute_label_id(**BASE)


@pytest.mark.parametrize(
    ("field", "other"),
    [
        ("sample_key", "log:2:1"),
        ("judge_name", "beta"),
        ("prompt_sha256", "b" * 64),
        ("model_id", "openai/gpt-5.6-sol"),
        ("label", "identifies_incorrect_step"),
        ("message_index", 0),
        ("char_start", 5),
        ("char_end", 11),
    ],
)
def test_changing_any_one_field_changes_the_id(field: str, other: object):
    assert compute_label_id(**{**BASE, field: other}) != compute_label_id(**BASE)


def test_a_zero_span_is_distinguishable_from_no_span():
    # This is why None hashes as "" rather than as a sentinel integer: a label
    # anchored at offset 0 and an unresolved label must not collide.
    zero = compute_label_id(**{**BASE, "char_start": 0, "char_end": 0})
    absent = compute_label_id(**{**BASE, "char_start": None, "char_end": None})
    assert zero != absent


def test_message_index_zero_is_distinguishable_from_no_message_index():
    zero = compute_label_id(**{**BASE, "message_index": 0})
    absent = compute_label_id(**{**BASE, "message_index": None})
    assert zero != absent


def test_the_field_separator_cannot_occur_in_a_field_value():
    # A unit separator is not producible by a judge name, sample key or label,
    # so field boundaries are unambiguous and no shifted concatenation collides.
    assert HASH_SEP == "\x1f"
    shifted_left = compute_label_id(**{**BASE, "judge_name": "alph", "prompt_sha256": "a" * 65})
    assert shifted_left != compute_label_id(**BASE)
