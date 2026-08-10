"""Surface selection and the blinding perimeter.

The judge sees construct and rubric, and a transcript stripped of anything that
could tell it the answer or the experimental arm.
"""

from __future__ import annotations

import pytest

from transcript_judge.models import Message, TranscriptSample
from transcript_judge.render import (
    DENYLISTED_METADATA_KEYS,
    SURFACES,
    BlindingViolation,
    assert_blinded,
    assign_render_ids,
    check_metadata_keys,
    render_sample,
    select_messages,
)


def test_surfaces_are_pinned():
    assert SURFACES == ("full", "assistant_only", "final_answer")


# --- surface selection -------------------------------------------------------


def test_full_surface_keeps_every_message(two_message_sample):
    messages, fallback = select_messages(two_message_sample, "full")
    assert [m.index for m in messages] == [0, 1]
    assert fallback is False


def test_assistant_only_drops_the_user_turn(two_message_sample):
    messages, fallback = select_messages(two_message_sample, "assistant_only")
    assert [m.index for m in messages] == [1]
    assert fallback is False


def test_final_answer_selects_the_phase_marked_messages(phased_sample):
    messages, fallback = select_messages(phased_sample, "final_answer")
    assert [m.index for m in messages] == [1, 5, 9]
    assert fallback is False


def test_unknown_surface_is_refused(two_message_sample):
    with pytest.raises(ValueError, match="unknown surface"):
        select_messages(two_message_sample, "cot_only")


def test_final_answer_falls_back_to_the_last_assistant_when_no_phases_exist(
    two_message_sample,
):
    # The real ProtocolQA logs carry no message_phase at all (surveyed
    # 2026-08-09, 13 logs, all None). Returning nothing here would hand the
    # judge an empty transcript and produce a confidently empty result.
    messages, fallback = select_messages(two_message_sample, "final_answer")
    assert [m.index for m in messages] == [1]
    assert fallback is True


def test_fallback_is_not_used_when_some_phase_exists_but_none_is_final():
    sample = TranscriptSample(
        sample_key="k:1:1",
        source_path="/fake.jsonl",
        messages=[
            Message(role="user", text="q", index=0, phase="reasoning"),
            Message(role="assistant", text="a", index=1, phase="reasoning"),
        ],
    )
    messages, fallback = select_messages(sample, "final_answer")
    assert messages == []
    assert fallback is False


def test_sample_with_no_assistant_message_yields_nothing():
    # One real log (K7oXgU9UeM) has samples with a user turn and no reply.
    sample = TranscriptSample(
        sample_key="k:1:1",
        source_path="/fake.jsonl",
        messages=[Message(role="user", text="q", index=0)],
    )
    messages, fallback = select_messages(sample, "final_answer")
    assert messages == []
    assert fallback is True


# --- render ids --------------------------------------------------------------


def test_render_ids_follow_sorted_sample_key_order_not_input_order():
    def sample(key: str) -> TranscriptSample:
        return TranscriptSample(sample_key=key, source_path="/fake", messages=[])

    ids = assign_render_ids([sample("zeta:9:1"), sample("alpha:1:1"), sample("mid:5:1")])
    assert ids == {"alpha:1:1": "s0001", "mid:5:1": "s0002", "zeta:9:1": "s0003"}


def test_render_ids_are_zero_padded_to_four_digits():
    samples = [
        TranscriptSample(sample_key=f"log:{i:04d}:1", source_path="/fake", messages=[])
        for i in range(3)
    ]
    assert sorted(assign_render_ids(samples).values()) == ["s0001", "s0002", "s0003"]


# --- the denylist ------------------------------------------------------------


def test_denylist_contents_are_pinned():
    assert (
        frozenset({"ideal", "distractors", "grading", "scores", "target"})
        == DENYLISTED_METADATA_KEYS
    )


@pytest.mark.parametrize("key", ["ideal", "distractors", "grading", "scores", "target"])
def test_each_denylisted_key_is_refused(key: str):
    with pytest.raises(BlindingViolation, match="cannot be overridden"):
        check_metadata_keys([key])


def test_the_refusal_names_the_offending_key():
    with pytest.raises(BlindingViolation, match="'ideal'"):
        check_metadata_keys(["subtask", "ideal"])


def test_an_allowed_metadata_key_passes():
    assert check_metadata_keys(["subtask", "difficulty"]) is None


def test_render_refuses_a_denylisted_key_rather_than_dropping_it(two_message_sample):
    with pytest.raises(BlindingViolation):
        render_sample(
            two_message_sample,
            surface="full",
            render_id="s0001",
            include_metadata=["ideal"],
        )


# --- what actually reaches the prompt ---------------------------------------


def test_rendered_text_identifies_the_sample_only_by_its_opaque_id(two_message_sample):
    rendered = render_sample(two_message_sample, surface="full", render_id="s0001")
    assert rendered.text.startswith("sample: s0001\n")
    assert "cot-hidden-sandbagging" not in rendered.text
    assert two_message_sample.sample_key not in rendered.text


def test_rendered_text_omits_the_reference_answer(two_message_sample):
    rendered = render_sample(two_message_sample, surface="full", render_id="s0001")
    assert "the reference answer text" not in rendered.text
    assert "ideal" not in rendered.text


def test_stored_indices_are_shown_with_their_gaps_intact(phased_sample):
    rendered = render_sample(phased_sample, surface="final_answer", render_id="s0001")
    assert rendered.included_indices == [1, 5, 9]
    assert "[message 1] role=assistant" in rendered.text
    assert "[message 5] role=assistant" in rendered.text
    assert "[message 9] role=assistant" in rendered.text
    # Renumbering to 0..2 would make every returned message_index point at the
    # wrong stored message.
    assert "[message 0]" not in rendered.text
    assert "[message 2]" not in rendered.text


def test_message_text_is_carried_through_verbatim(two_message_sample):
    rendered = render_sample(two_message_sample, surface="assistant_only", render_id="s0007")
    assert "The 300 µL volume looks wrong; I'd expect 1 mL per 10⁷ cells." in rendered.text
    assert rendered.render_id == "s0007"
    assert rendered.surface == "assistant_only"


def test_an_allowlisted_metadata_key_is_shown(two_message_sample):
    rendered = render_sample(
        two_message_sample,
        surface="full",
        render_id="s0001",
        include_metadata=["subtask"],
    )
    assert "  subtask: rna" in rendered.text


def test_metadata_absent_from_the_sample_is_simply_not_shown(two_message_sample):
    rendered = render_sample(
        two_message_sample,
        surface="full",
        render_id="s0001",
        include_metadata=["difficulty"],
    )
    assert "metadata:" not in rendered.text


# --- the belt-and-braces check ----------------------------------------------


def test_assert_blinded_accepts_a_clean_render(two_message_sample):
    rendered = render_sample(two_message_sample, surface="full", render_id="s0001")
    assert assert_blinded(rendered.text, two_message_sample) is None


def test_assert_blinded_rejects_a_render_carrying_the_sample_key(two_message_sample):
    leaked = "sample: cot-hidden-sandbagging-log:abc123:1\n\nbody\n"
    with pytest.raises(BlindingViolation, match="sample_key"):
        assert_blinded(leaked, two_message_sample)


def test_assert_blinded_rejects_a_render_carrying_the_reference_answer(two_message_sample):
    leaked = "sample: s0001\n\nhint: the reference answer text\n"
    with pytest.raises(BlindingViolation, match="denylisted metadata key 'ideal'"):
        assert_blinded(leaked, two_message_sample)
