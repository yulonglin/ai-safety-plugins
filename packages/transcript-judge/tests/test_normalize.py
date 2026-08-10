"""The stored text is the text: no stripping, no collapsing, nothing normalised."""

from __future__ import annotations

from transcript_judge.normalize import (
    BLOCK_JOIN,
    NORMALIZER_VERSION,
    message_phase,
    message_text,
    stable_dumps,
)


def test_string_content_is_used_verbatim_including_padding():
    message = {"role": "user", "content": "  leading and trailing  "}
    assert message_text(message) == "  leading and trailing  "


def test_internal_double_space_survives():
    message = {"role": "user", "content": "300 µL  cold TRIzol"}
    assert message_text(message) == "300 µL  cold TRIzol"


def test_text_blocks_join_with_a_blank_line():
    message = {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "first part"},
            {"type": "text", "text": "second part"},
        ],
    }
    assert message_text(message) == "first part\n\nsecond part"
    assert BLOCK_JOIN == "\n\n"


def test_non_text_block_becomes_a_counted_placeholder():
    message = {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "before"},
            {"type": "image", "source": {"data": "..."}},
            {"type": "text", "text": "after"},
        ],
    }
    stats: dict[str, int] = {}
    assert message_text(message, stats) == "before\n\n[non-text block: image]\n\nafter"
    assert stats["non_text_blocks_elided"] == 1


def test_two_non_text_blocks_count_twice():
    message = {
        "role": "assistant",
        "content": [
            {"type": "image", "source": {}},
            {"type": "tool_use", "name": "x"},
        ],
    }
    stats: dict[str, int] = {}
    message_text(message, stats)
    assert stats["non_text_blocks_elided"] == 2


def test_missing_content_is_empty_not_an_error():
    assert message_text({"role": "user"}) == ""


def test_phase_is_read_from_internal_and_is_none_when_absent():
    assert message_phase({"internal": {"message_phase": "final_answer"}}) == "final_answer"
    assert message_phase({"internal": None}) is None
    assert message_phase({}) is None


def test_stable_dumps_is_key_order_independent():
    a = stable_dumps({"b": 1, "a": 2})
    b = stable_dumps({"a": 2, "b": 1})
    assert a == b
    assert a == '{"a":2,"b":1}'


def test_stable_dumps_keeps_non_ascii_unescaped():
    assert stable_dumps({"t": "300 µL"}) == '{"t":"300 µL"}'


def test_normalizer_version_is_pinned():
    assert NORMALIZER_VERSION == 1
