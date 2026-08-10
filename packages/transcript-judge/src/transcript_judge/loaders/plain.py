"""Fallback loader: a single JSON document, or a raw text file as one message."""

from __future__ import annotations

import json
from pathlib import Path

from transcript_judge.loaders.jsonl import sample_from_obj
from transcript_judge.models import Message, TranscriptSample


def load_plain(path: str | Path, stats: dict[str, int] | None = None) -> list[TranscriptSample]:
    target = Path(path)
    raw = target.read_text(encoding="utf-8")

    if target.suffix.lower() == ".json":
        doc = json.loads(raw)
        objs = doc if isinstance(doc, list) else [doc]
        return [
            sample_from_obj(obj, source_path=target, fallback_id=str(i), stats=stats)
            for i, obj in enumerate(objs)
        ]

    return [
        TranscriptSample(
            sample_key=f"{target.stem}:0:1",
            source_path=str(target),
            messages=[Message(role="user", text=raw, index=0, phase=None)],
            extra={},
        )
    ]
