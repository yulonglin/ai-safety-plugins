"""Surface selection, the blinding perimeter, and message numbering.

Everything a judge ever sees is built here, from an **allowlist**: the role and
text of each message in the selected surface, plus an opaque sample id. Nothing
is copied across from `scores`, and nothing from `extra["metadata"]` unless the
caller names the key explicitly.

Two rules that look like details and are not:

* **Message numbers are stored indices.** Under a narrowing surface the judge
  sees ``[message 1]``, ``[message 5]``, ``[message 9]`` with gaps. Renumbering
  the filtered subset to ``0..n`` would make every returned `message_index`
  point at the wrong message in the stored transcript.
* **`sample_key` never enters a prompt.** It embeds the log stem, and log
  filenames in this corpus carry arm identity (``negative-control``,
  ``cot-hidden-sandbagging``). The judge gets ``s0001`` instead.
"""

from __future__ import annotations

from pydantic import BaseModel

from transcript_judge.models import Message, Surface, TranscriptSample

#: Keys that would hand the judge the answer or another grader's verdict. This
#: is a hard denylist: `--include-metadata` cannot override it, and naming one
#: exits non-zero rather than warning. `grading` is absent from the ProtocolQA
#: logs surveyed on 2026-08-09 but stays here -- the cost of listing a key that
#: never appears is nil, the cost of the reverse is a leaked run.
DENYLISTED_METADATA_KEYS = frozenset({"ideal", "distractors", "grading", "scores", "target"})

SURFACES: tuple[Surface, ...] = ("full", "assistant_only", "final_answer")

FINAL_ANSWER_PHASE = "final_answer"


class BlindingViolation(ValueError):
    """Raised when a run would hand the judge something it must not see."""


class RenderedSample(BaseModel):
    """What was actually sent, plus the bookkeeping needed to read it back."""

    sample_key: str
    render_id: str
    surface: Surface
    text: str
    #: Stored indices of the messages included, in emission order. This is the
    #: list a `message_index` from the judge is validated against.
    included_indices: list[int]
    #: True when `final_answer` had no phase markers to work from.
    final_answer_fallback: bool = False


def assign_render_ids(samples: list[TranscriptSample]) -> dict[str, str]:
    """Opaque ids ``s0001``, ``s0002``, ... in sorted `sample_key` order.

    Sorted rather than input order so the mapping is reproducible across runs
    regardless of how the loader happened to enumerate files.
    """
    return {
        key: f"s{i:04d}" for i, key in enumerate(sorted({s.sample_key for s in samples}), start=1)
    }


def check_metadata_keys(keys: list[str]) -> None:
    """Reject denylisted `--include-metadata` keys. Non-overridable by design."""
    bad = sorted({k for k in keys if k in DENYLISTED_METADATA_KEYS})
    if bad:
        raise BlindingViolation(
            "refusing to include metadata key(s) "
            + ", ".join(repr(k) for k in bad)
            + ": these carry the reference answer or another grader's verdict, and a judge "
            "that sees them is not measuring what the run claims to measure. "
            "This denylist cannot be overridden."
        )


def select_messages(sample: TranscriptSample, surface: Surface) -> tuple[list[Message], bool]:
    """Return the messages for `surface`, plus whether a fallback was used."""
    if surface == "full":
        return list(sample.messages), False
    if surface == "assistant_only":
        return [m for m in sample.messages if m.role == "assistant"], False
    if surface != "final_answer":
        raise ValueError(f"unknown surface {surface!r}; expected one of {', '.join(SURFACES)}")

    phased = [m for m in sample.messages if m.phase == FINAL_ANSWER_PHASE]
    if phased:
        return phased, False

    # No phase markers anywhere in this sample. Returning nothing would hand the
    # judge an empty transcript and produce a confidently empty result, so fall
    # back to the last assistant message and count it in the manifest.
    if any(m.phase is not None for m in sample.messages):
        return [], False
    assistants = [m for m in sample.messages if m.role == "assistant"]
    return (assistants[-1:], True) if assistants else ([], True)


def render_sample(
    sample: TranscriptSample,
    *,
    surface: Surface,
    render_id: str,
    include_metadata: list[str] | None = None,
) -> RenderedSample:
    """Build the blinded transcript text for one sample."""
    include_metadata = include_metadata or []
    check_metadata_keys(include_metadata)

    messages, fallback = select_messages(sample, surface)

    lines = [f"sample: {render_id}", ""]

    if include_metadata:
        metadata = sample.extra.get("metadata") or {}
        shown = {k: metadata[k] for k in include_metadata if k in metadata}
        if shown:
            lines.append("metadata:")
            lines.extend(f"  {k}: {shown[k]}" for k in sorted(shown))
            lines.append("")

    for message in messages:
        lines.append(f"[message {message.index}] role={message.role}")
        lines.append(message.text)
        lines.append("")

    return RenderedSample(
        sample_key=sample.sample_key,
        render_id=render_id,
        surface=surface,
        text="\n".join(lines).rstrip("\n") + "\n",
        included_indices=[m.index for m in messages],
        final_answer_fallback=fallback,
    )


def assert_blinded(rendered: str, sample: TranscriptSample) -> None:
    """Belt-and-braces check that no forbidden string reached the prompt.

    Cheap enough to run on every render, and it catches the failure mode the
    allowlist is meant to prevent if someone later adds a field to the renderer.
    """
    if sample.sample_key in rendered:
        raise BlindingViolation(
            f"rendered input contains the sample_key {sample.sample_key!r}, which embeds "
            "the log stem and therefore the experimental arm"
        )
    metadata = sample.extra.get("metadata") or {}
    for key in DENYLISTED_METADATA_KEYS:
        value = metadata.get(key)
        if isinstance(value, str) and len(value) >= 24 and value in rendered:
            raise BlindingViolation(
                f"rendered input contains the value of denylisted metadata key {key!r}"
            )
