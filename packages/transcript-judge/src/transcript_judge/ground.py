"""Quote -> character span, via a four-tier ladder.

A judge returns a quote it believes is verbatim. Often it is; often it has
straightened a curly apostrophe, collapsed a double space, or recomposed an
accent. The ladder tries progressively more forgiving matches and **records
which tier succeeded**, so a run's grounding quality is a number rather than an
impression.

Every tier folds a *copy* and maps the match back through a per-character index
table, so the returned span always indexes the untouched stored text. The
resulting `source_excerpt` is produced by slicing that stored text, which makes
``stored_text[char_start:char_end] == source_excerpt`` true by construction at
every tier -- not merely asserted.

Offsets are Python codepoint indices (``offset_unit: "codepoint"``). This corpus
is full of ``µ``, ``°C``, ``×`` and en-dashes, so a byte offset would be wrong
roughly wherever it mattered.
"""

from __future__ import annotations

import unicodedata

from pydantic import BaseModel

from transcript_judge.models import Message, ResolutionTier

#: Tried in order; the first hit wins and is recorded.
TIER_ORDER: tuple[ResolutionTier, ...] = ("exact", "nfc", "punct_fold", "ws_collapse")

#: Characters a model routinely "tidies" when quoting.
PUNCT_FOLD = {
    "‘": "'",
    "’": "'",
    "‚": "'",
    "‛": "'",
    "“": '"',
    "”": '"',
    "„": '"',
    "‟": '"',
    "′": "'",
    "″": '"',
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",
    "—": "-",
    "―": "-",
    "−": "-",
    " ": " ",
    "…": "...",
}


class GroundResult(BaseModel):
    resolved: bool
    resolution_tier: ResolutionTier
    message_index: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    source_excerpt: str | None = None
    occurrence_count: int = 0
    message_index_corrected: bool = False


def _fold(text: str, tier: ResolutionTier) -> tuple[str, list[int]]:
    """Fold `text` for `tier`, returning the folded string and an index map.

    ``index_map[i]`` is the index in the original `text` of the character that
    produced folded character ``i``.
    """
    if tier == "exact":
        return text, list(range(len(text)))

    out: list[str] = []
    index_map: list[int] = []
    pending_space = False

    for i, ch in enumerate(text):
        if tier == "ws_collapse" and ch.isspace():
            # Emit at most one space per run of whitespace.
            pending_space = True
            continue
        if pending_space:
            out.append(" ")
            index_map.append(i)
            pending_space = False

        folded = unicodedata.normalize("NFC", ch)
        if tier in {"punct_fold", "ws_collapse"}:
            folded = "".join(PUNCT_FOLD.get(c, c) for c in folded)

        for c in folded:
            out.append(c)
            index_map.append(i)

    return "".join(out), index_map


def _count_non_overlapping(haystack: str, needle: str) -> int:
    if not needle:
        return 0
    count = 0
    start = 0
    while True:
        found = haystack.find(needle, start)
        if found < 0:
            return count
        count += 1
        start = found + len(needle)


def resolve_in_text(quote: str, text: str) -> GroundResult:
    """Try each tier against one message's stored text."""
    for tier in TIER_ORDER:
        folded_text, index_map = _fold(text, tier)
        folded_quote, _ = _fold(quote, tier)
        if tier == "ws_collapse":
            folded_quote = folded_quote.strip()
        if not folded_quote:
            continue

        hit = folded_text.find(folded_quote)
        if hit < 0:
            continue

        start = index_map[hit]
        end = index_map[hit + len(folded_quote) - 1] + 1
        return GroundResult(
            resolved=True,
            resolution_tier=tier,
            char_start=start,
            char_end=end,
            # Sliced, never reconstructed: this is what makes the span/excerpt
            # invariant hold at the folding tiers too.
            source_excerpt=text[start:end],
            occurrence_count=_count_non_overlapping(folded_text, folded_quote),
        )

    return GroundResult(resolved=False, resolution_tier="unresolved")


def ground_quote(
    quote: str | None,
    messages: list[Message],
    stated_index: int | None,
) -> GroundResult:
    """Locate `quote` among the messages the judge actually saw.

    The stated message is tried first. If the quote is not there but is found in
    another visible message, the span is taken from that message and
    `message_index_corrected` is set -- a wrong index is a bookkeeping slip,
    while dropping the label would lose a real finding.
    """
    if not quote:
        return GroundResult(resolved=False, resolution_tier="unresolved")

    by_index = {m.index: m for m in messages}

    if stated_index is not None and stated_index in by_index:
        result = resolve_in_text(quote, by_index[stated_index].text)
        if result.resolved:
            result.message_index = stated_index
            return result

    for message in messages:
        if message.index == stated_index:
            continue
        result = resolve_in_text(quote, message.text)
        if result.resolved:
            result.message_index = message.index
            result.message_index_corrected = stated_index is not None
            return result

    return GroundResult(
        resolved=False,
        resolution_tier="unresolved",
        message_index=stated_index,
    )
