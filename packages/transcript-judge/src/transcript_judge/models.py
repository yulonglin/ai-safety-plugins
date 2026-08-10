"""Every pydantic model in the pipeline.

The one structural decision worth stating here: the unit of measurement is the
*judge cell* -- ``(judge_name, prompt_sha256, model_id)`` -- not the judge name.
Anything that counts, compares, resumes or de-duplicates takes a `JudgeCell`
rather than three loose strings, so a forgotten `model_id` is a type error
instead of a silently collapsed dimension.
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Surface = Literal["full", "assistant_only", "final_answer"]
EvidenceMode = Literal["positive_quote", "hand_validation"]
ResolutionTier = Literal["exact", "nfc", "punct_fold", "ws_collapse", "unresolved"]

#: Field separator for every id hash in this package. A unit separator cannot
#: occur in a sample key, judge name or label, so concatenation is unambiguous.
HASH_SEP = "\x1f"


class JudgeCell(BaseModel):
    """The unit of measurement. Frozen so it can key a dict or live in a set."""

    model_config = ConfigDict(frozen=True)

    judge_name: str
    prompt_sha256: str
    model_id: str

    def as_tuple(self) -> tuple[str, str, str]:
        return (self.judge_name, self.prompt_sha256, self.model_id)

    @property
    def slug(self) -> str:
        """Short human-facing identifier; not used as a key."""
        return f"{self.judge_name}@{self.prompt_sha256[:8]}/{self.model_id}"


class Message(BaseModel):
    """One message of a transcript, already normalised to text."""

    role: str
    text: str
    index: int
    phase: str | None = None


class TranscriptSample(BaseModel):
    sample_key: str
    source_path: str
    messages: list[Message]
    extra: dict[str, Any] = Field(default_factory=dict)


class JudgeSpec(BaseModel):
    """A versioned prompt file resolved against one provider/model."""

    name: str
    prompt_path: str
    prompt_text: str
    prompt_sha256: str
    provider: str
    model_id: str
    surface: Surface
    params: dict[str, Any] = Field(default_factory=dict)
    schema_fields: list[SchemaField] = Field(default_factory=list)

    @property
    def cell(self) -> JudgeCell:
        return JudgeCell(
            judge_name=self.name,
            prompt_sha256=self.prompt_sha256,
            model_id=self.model_id,
        )


class SchemaField(BaseModel):
    """One declared output field of a judge prompt.

    `evidence_mode` is *declared*, never inferred from the field name. Name
    patterns (``never_``, ``_absent``) miss ``omits_warning`` and
    ``fails_to_acknowledge`` and fail open, which is the wrong direction.
    """

    name: str
    description: str
    evidence_mode: EvidenceMode


class Finding(BaseModel):
    """One judge verdict on one declared field.

    Field order is the emission order: the rationale is committed before the
    value, so the model reasons before it decides.
    """

    field: str
    rationale: str
    value: bool
    quote: str | None = None
    message_index: int | None = None


class JudgeResponse(BaseModel):
    """The single output grammar shared by every provider and every prompt."""

    model_config = ConfigDict(extra="forbid")

    findings: list[Finding]


class RawCompletion(BaseModel):
    """Provider-agnostic result of one API call."""

    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    raw_json: dict[str, Any] = Field(default_factory=dict)


class ParseError(BaseModel):
    message: str
    raw_text: str


class JudgementRow(BaseModel):
    """One append-only row: exactly what was sent, exactly what came back."""

    sample_key: str
    judge_name: str
    prompt_sha256: str
    model_id: str
    provider: str
    surface: Surface
    rendered_input: str
    raw_output: str
    parsed: dict[str, Any] | None = None
    parse_ok: bool = False
    parse_error: str | None = None
    attempt: int = 1
    tokens_in: int = 0
    tokens_out: int = 0
    timestamp_utc: str = ""
    normalizer_version: int = 0

    @property
    def cell(self) -> JudgeCell:
        return JudgeCell(
            judge_name=self.judge_name,
            prompt_sha256=self.prompt_sha256,
            model_id=self.model_id,
        )


def compute_label_id(
    *,
    sample_key: str,
    judge_name: str,
    prompt_sha256: str,
    model_id: str,
    label: str,
    message_index: int | None,
    char_start: int | None,
    char_end: int | None,
) -> str:
    """Stable 16-hex id over exactly the eight identity fields.

    Unresolved rows and `hand_validation` fields have no span; they hash the
    empty string in those positions rather than a sentinel integer, so a span
    of 0 stays distinguishable from the absence of a span.
    """
    parts = [
        sample_key,
        judge_name,
        prompt_sha256,
        model_id,
        label,
        "" if message_index is None else str(message_index),
        "" if char_start is None else str(char_start),
        "" if char_end is None else str(char_end),
    ]
    digest = hashlib.sha256(HASH_SEP.join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


class LabelRow(BaseModel):
    """A grounded finding.

    Two excerpt fields, deliberately: `judge_quote` is the model's output and is
    never mutated; `source_excerpt` is always exactly
    ``stored_text[char_start:char_end]``. They are equal only at the `exact`
    tier -- at every other tier the divergence between them *is* the record of
    what the grounding ladder had to fold to find the span.
    """

    label_id: str
    sample_key: str
    label: str
    evidence_mode: EvidenceMode
    value: bool
    judge_quote: str | None = None
    source_excerpt: str | None = None
    message_index: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    occurrence_count: int = 0
    offset_unit: Literal["codepoint"] = "codepoint"
    resolved: bool = False
    resolution_tier: ResolutionTier = "unresolved"
    message_index_corrected: bool = False
    judge_name: str
    prompt_sha256: str
    model_id: str
    surface: Surface
    judgement_row_id: str

    @property
    def cell(self) -> JudgeCell:
        return JudgeCell(
            judge_name=self.judge_name,
            prompt_sha256=self.prompt_sha256,
            model_id=self.model_id,
        )


class ClusterAssignment(BaseModel):
    cluster_id: int
    canonical_label: str
    members: list[str]
    label_ids: list[str]


class PairVerdict(BaseModel):
    """One cached merge-judge decision on an unordered pair.

    A cached verdict replays forever, so the row has to carry its own evidence:
    the rationale the judge committed to before deciding, the quote when it
    offered one, and the tokens the call cost. This row -- not a manifest
    counter -- is the reconstructable record of what the merge path decided and
    what it spent, because the counter only ever describes one invocation.

    ``parse_ok`` separates a judged negative from a call whose response could
    not be read. Both leave ``equivalent`` false; only one of them is a
    decision, and without the flag a billed failure replays as a verdict.
    """

    canon_a: str
    canon_b: str
    merge_prompt_sha256: str
    model_id: str
    equivalent: bool
    rationale: str = ""
    quote: str | None = None
    parse_ok: bool = True
    tokens_in: int = 0
    tokens_out: int = 0


JudgeSpec.model_rebuild()
