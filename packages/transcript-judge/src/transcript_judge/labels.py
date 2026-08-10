"""Judgement rows -> grounded label rows.

A `LabelRow` is emitted for **every** finding, positive or negative, so the
denominator of any later rate is the number of questions actually asked rather
than the number that happened to come back true.

Grounding is attempted only for positive `positive_quote` findings.
`hand_validation` fields assert an absence: a judge asked to quote an absence
will supply an irrelevant quote to satisfy the instruction, so their quote field
is never treated as evidence and never enters clustering or the artifact.
"""

from __future__ import annotations

from pydantic import BaseModel

from transcript_judge.ground import GroundResult, ground_quote
from transcript_judge.models import (
    EvidenceMode,
    LabelRow,
    Message,
    TranscriptSample,
    compute_label_id,
)
from transcript_judge.render import select_messages


class LabelStats(BaseModel):
    labels_total: int = 0
    labels_positive: int = 0
    labels_unresolved: int = 0
    labels_hand_validation: int = 0
    message_index_corrected_count: int = 0
    resolution_tier_counts: dict[str, int] = {}


def derive_labels(
    *,
    rows: list[dict],
    samples_by_key: dict[str, TranscriptSample],
    field_modes: dict[tuple[str, str], dict[str, EvidenceMode]],
    row_ids: list[str],
) -> tuple[list[LabelRow], LabelStats]:
    """Build label rows from parsed judgement rows.

    `field_modes` maps ``(judge_name, prompt_sha256)`` to the declared
    evidence mode of each field, taken from the manifest so that a prompt file
    edited after the run cannot retroactively change how its rows are read.
    """
    labels: list[LabelRow] = []
    stats = LabelStats(resolution_tier_counts={})

    for row, row_id in zip(rows, row_ids, strict=True):
        if not row.get("parse_ok"):
            continue

        sample = samples_by_key.get(row["sample_key"])
        if sample is None:
            continue

        visible: list[Message]
        visible, _ = select_messages(sample, row["surface"])
        modes = field_modes.get((row["judge_name"], row["prompt_sha256"]), {})

        for finding in (row.get("parsed") or {}).get("findings", []):
            field = finding["field"]
            mode: EvidenceMode = modes.get(field, "positive_quote")
            value = bool(finding["value"])

            should_ground = value and mode == "positive_quote"
            result = (
                ground_quote(finding.get("quote"), visible, finding.get("message_index"))
                if should_ground
                else GroundResult(resolved=False, resolution_tier="unresolved")
            )

            labels.append(
                LabelRow(
                    label_id=compute_label_id(
                        sample_key=row["sample_key"],
                        judge_name=row["judge_name"],
                        prompt_sha256=row["prompt_sha256"],
                        model_id=row["model_id"],
                        label=field,
                        message_index=result.message_index,
                        char_start=result.char_start,
                        char_end=result.char_end,
                    ),
                    sample_key=row["sample_key"],
                    label=field,
                    evidence_mode=mode,
                    value=value,
                    judge_quote=finding.get("quote"),
                    source_excerpt=result.source_excerpt,
                    message_index=result.message_index,
                    char_start=result.char_start,
                    char_end=result.char_end,
                    occurrence_count=result.occurrence_count,
                    resolved=result.resolved,
                    resolution_tier=result.resolution_tier,
                    message_index_corrected=result.message_index_corrected,
                    judge_name=row["judge_name"],
                    prompt_sha256=row["prompt_sha256"],
                    model_id=row["model_id"],
                    surface=row["surface"],
                    judgement_row_id=row_id,
                )
            )

            stats.labels_total += 1
            if mode == "hand_validation":
                stats.labels_hand_validation += 1
            if value:
                stats.labels_positive += 1
            if should_ground:
                tier = result.resolution_tier
                stats.resolution_tier_counts[tier] = stats.resolution_tier_counts.get(tier, 0) + 1
                if not result.resolved:
                    stats.labels_unresolved += 1
                if result.message_index_corrected:
                    stats.message_index_corrected_count += 1

    return labels, stats


def verify_spans(labels: list[LabelRow], samples_by_key: dict[str, TranscriptSample]) -> list[str]:
    """Re-check the span/excerpt invariant against the stored transcripts.

    Cheap, and it is the acceptance criterion stated in the spec, so it runs as
    a check rather than living only in the test-suite.
    """
    problems: list[str] = []
    for label in labels:
        if not label.resolved or label.char_start is None or label.char_end is None:
            continue
        sample = samples_by_key.get(label.sample_key)
        if sample is None:
            problems.append(f"{label.label_id}: sample {label.sample_key} missing")
            continue
        message = next((m for m in sample.messages if m.index == label.message_index), None)
        if message is None:
            problems.append(f"{label.label_id}: message {label.message_index} missing")
            continue
        if message.text[label.char_start : label.char_end] != label.source_excerpt:
            problems.append(
                f"{label.label_id}: span [{label.char_start},{label.char_end}) does not "
                "reproduce source_excerpt"
            )
    return problems
