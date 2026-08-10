"""The grounding ladder, and the invariant that makes a span trustworthy.

Every resolved label must satisfy ``stored_text[char_start:char_end] ==
source_excerpt`` -- at the folding tiers too, not only at `exact`.
"""

from __future__ import annotations

import pytest

from transcript_judge.ground import TIER_ORDER, ground_quote, resolve_in_text
from transcript_judge.models import Message

#: Non-ASCII on purpose. A byte offset would be wrong from the micro sign on.
TEXT = "Add 300 µL  cold TRIzol – then vortex the 300 µL aliquot."


def test_tier_order_is_pinned():
    assert TIER_ORDER == ("exact", "nfc", "punct_fold", "ws_collapse")


def test_exact_match_reports_codepoint_offsets():
    result = resolve_in_text("300 µL", TEXT)
    assert result.resolved is True
    assert result.resolution_tier == "exact"
    assert (result.char_start, result.char_end) == (4, 10)
    assert result.source_excerpt == "300 µL"
    assert TEXT[4:10] == "300 µL"


def test_exact_match_counts_non_overlapping_occurrences():
    result = resolve_in_text("300 µL", TEXT)
    assert result.occurrence_count == 2


def test_en_dash_straightened_by_the_judge_resolves_at_punct_fold():
    # The judge wrote an ASCII hyphen; the transcript has an en-dash.
    result = resolve_in_text("TRIzol - then", TEXT)
    assert result.resolved is True
    assert result.resolution_tier == "punct_fold"
    assert result.source_excerpt == "TRIzol – then"
    assert TEXT[result.char_start : result.char_end] == result.source_excerpt


def test_collapsed_double_space_resolves_at_ws_collapse():
    # The judge wrote one space; the transcript has two.
    result = resolve_in_text("µL cold TRIzol", TEXT)
    assert result.resolved is True
    assert result.resolution_tier == "ws_collapse"
    assert result.source_excerpt == "µL  cold TRIzol"
    assert TEXT[result.char_start : result.char_end] == result.source_excerpt


def test_curly_apostrophe_resolves_at_punct_fold():
    text = "I’d expect 1 mL per sample."
    result = resolve_in_text("I'd expect", text)
    assert result.resolved is True
    assert result.resolution_tier == "punct_fold"
    assert result.source_excerpt == "I’d expect"
    assert text[result.char_start : result.char_end] == result.source_excerpt


def test_absent_quote_is_unresolved_and_carries_no_span():
    result = resolve_in_text("this phrase never appears", TEXT)
    assert result.resolved is False
    assert result.resolution_tier == "unresolved"
    assert result.char_start is None
    assert result.char_end is None
    assert result.source_excerpt is None


@pytest.mark.parametrize(
    "quote",
    ["300 µL", "TRIzol - then", "µL cold TRIzol", "vortex"],
)
def test_span_reproduces_excerpt_at_every_tier(quote: str):
    result = resolve_in_text(quote, TEXT)
    assert result.resolved is True
    assert TEXT[result.char_start : result.char_end] == result.source_excerpt


def _messages() -> list[Message]:
    return [
        Message(role="user", text="The protocol says to add 300 µL of TRIzol.", index=0),
        Message(role="assistant", text=TEXT, index=1),
    ]


def test_quote_found_in_the_stated_message_is_not_flagged_as_corrected():
    result = ground_quote("vortex", _messages(), 1)
    assert result.resolved is True
    assert result.message_index == 1
    assert result.message_index_corrected is False


def test_quote_found_elsewhere_corrects_the_index_rather_than_dropping_the_label():
    # The judge said message 0; the text is only in message 1.
    result = ground_quote("vortex", _messages(), 0)
    assert result.resolved is True
    assert result.message_index == 1
    assert result.message_index_corrected is True


def test_unresolvable_quote_keeps_the_stated_index_for_inspection():
    result = ground_quote("no such text anywhere", _messages(), 1)
    assert result.resolved is False
    assert result.message_index == 1


def test_empty_quote_is_unresolved():
    assert ground_quote(None, _messages(), 0).resolved is False
    assert ground_quote("", _messages(), 0).resolved is False
