"""Inspect AI `.eval` loader. `inspect_ai` is an optional extra, imported lazily."""

from __future__ import annotations

from pathlib import Path

from transcript_judge.models import Message, TranscriptSample
from transcript_judge.normalize import message_phase, message_text

#: Inspect writes oversized content out-of-line and leaves a URI behind. We
#: always resolve attachments, so seeing one of these means the resolution
#: silently failed and the judge would have scored a placeholder.
ATTACHMENT_PREFIX = "attachment://"


class AttachmentUnresolvedError(RuntimeError):
    pass


def load_eval(path: str | Path, stats: dict[str, int] | None = None) -> list[TranscriptSample]:
    try:
        from inspect_ai.log import read_eval_log
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ImportError(
            "reading .eval logs needs the 'inspect' extra: "
            "uv run --project packages/transcript-judge --with inspect-ai tj load ..."
        ) from exc

    target = Path(path)
    log = read_eval_log(str(target), resolve_attachments=True)
    log_stem = target.stem

    samples: list[TranscriptSample] = []
    for sample in log.samples or []:
        messages: list[Message] = []
        for index, raw in enumerate(sample.messages):
            text = message_text(raw, stats=stats)
            if text.startswith(ATTACHMENT_PREFIX):
                raise AttachmentUnresolvedError(
                    f"{target}: message {index} of sample {sample.id} still holds an "
                    f"unresolved attachment URI ({text[:60]!r}). The judge would have "
                    "scored the placeholder rather than the transcript."
                )
            messages.append(
                Message(
                    role=str(raw.role),
                    text=text,
                    index=index,
                    phase=message_phase(raw),
                )
            )

        samples.append(
            TranscriptSample(
                sample_key=f"{log_stem}:{sample.id}:{sample.epoch}",
                source_path=str(target),
                messages=messages,
                extra={
                    "epoch": sample.epoch,
                    "sample_id": str(sample.id),
                    # Stored so a human reviewer and the denylist check can both
                    # see it. `render` never reads `extra` except for keys named
                    # explicitly via --include-metadata, and refuses the
                    # denylisted ones outright.
                    "metadata": dict(sample.metadata or {}),
                },
            )
        )
    return samples
