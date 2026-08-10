"""Transcript loading: path (or directory of paths) -> `TranscriptSample` list."""

from __future__ import annotations

from pathlib import Path

from transcript_judge.models import TranscriptSample

FORMATS = ("auto", "inspect_eval", "jsonl", "plain")


def detect_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".eval":
        return "inspect_eval"
    if suffix in {".jsonl", ".ndjson"}:
        return "jsonl"
    return "plain"


def load(
    path: str | Path,
    format: str = "auto",
    stats: dict[str, int] | None = None,
) -> list[TranscriptSample]:
    """Load one file or every recognised file in a directory."""
    if format not in FORMATS:
        raise ValueError(f"unknown format {format!r}; expected one of {', '.join(FORMATS)}")

    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"no such transcript path: {target}")

    if target.is_dir():
        samples: list[TranscriptSample] = []
        for child in sorted(target.iterdir()):
            if child.is_file() and child.suffix.lower() in {
                ".eval",
                ".jsonl",
                ".ndjson",
                ".json",
                ".txt",
                ".md",
            }:
                samples.extend(load(child, format=format, stats=stats))
        return samples

    resolved = detect_format(target) if format == "auto" else format

    if resolved == "inspect_eval":
        from transcript_judge.loaders.inspect_eval import load_eval

        return load_eval(target, stats=stats)
    if resolved == "jsonl":
        from transcript_judge.loaders.jsonl import load_jsonl

        return load_jsonl(target, stats=stats)

    from transcript_judge.loaders.plain import load_plain

    return load_plain(target, stats=stats)


__all__ = ["FORMATS", "detect_format", "load"]
