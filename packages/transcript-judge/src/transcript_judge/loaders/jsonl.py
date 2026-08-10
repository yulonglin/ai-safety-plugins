"""JSONL loader: one sample per line, each with a `messages` list."""

from __future__ import annotations

import json
from pathlib import Path

from transcript_judge.models import Message, TranscriptSample
from transcript_judge.normalize import message_phase, message_text


def sample_from_obj(
    obj: dict,
    *,
    source_path: Path,
    fallback_id: str,
    stats: dict[str, int] | None = None,
) -> TranscriptSample:
    raw_messages = obj.get("messages") or []
    messages = [
        Message(
            role=str(raw.get("role", "user")),
            text=message_text(raw, stats=stats),
            index=index,
            phase=message_phase(raw),
        )
        for index, raw in enumerate(raw_messages)
    ]

    sample_id = str(obj.get("id", obj.get("sample_id", fallback_id)))
    epoch = obj.get("epoch", 1)
    sample_key = str(obj.get("sample_key") or f"{source_path.stem}:{sample_id}:{epoch}")

    extra = {k: v for k, v in obj.items() if k != "messages"}
    return TranscriptSample(
        sample_key=sample_key,
        source_path=str(source_path),
        messages=messages,
        extra=extra,
    )


def load_jsonl(path: str | Path, stats: dict[str, int] | None = None) -> list[TranscriptSample]:
    target = Path(path)
    samples: list[TranscriptSample] = []
    with open(target, encoding="utf-8") as handle:
        for line_no, line in enumerate(handle):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            samples.append(
                sample_from_obj(
                    obj,
                    source_path=target,
                    fallback_id=str(line_no),
                    stats=stats,
                )
            )
    return samples
