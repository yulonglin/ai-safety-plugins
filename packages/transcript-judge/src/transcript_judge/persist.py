"""Append-only JSONL, the run directory layout, and manifest assembly.

Two invariants hold everything else up:

* **Judgement files are append-only.** One file per *prompt*, holding every cell
  of that prompt interleaved. Resume filters within the file; `tj diff` groups
  within it. Nothing is ever rewritten, so a prompt edit leaves the prior rows
  byte-identical on disk.
* **Derived files are regenerated wholesale.** `labels.jsonl` and
  `clusters/assignments.json` are the only overwritable artefacts, and they are
  refused if the judgement files they were derived from have changed sha.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from transcript_judge.models import JudgeCell
from transcript_judge.normalize import sha256_text, stable_dumps


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class RunPaths:
    root: Path

    @property
    def manifest(self) -> Path:
        return self.root / "manifest.json"

    @property
    def transcripts(self) -> Path:
        return self.root / "transcripts.jsonl"

    @property
    def judgements_dir(self) -> Path:
        return self.root / "judgements"

    @property
    def labels(self) -> Path:
        return self.root / "labels.jsonl"

    @property
    def clusters_dir(self) -> Path:
        return self.root / "clusters"

    @property
    def artifact_dir(self) -> Path:
        return self.root / "artifact"

    @property
    def report(self) -> Path:
        return self.root / "report.md"

    def judgement_file(self, judge_name: str) -> Path:
        return self.judgements_dir / f"{judge_name}.jsonl"

    def ensure(self) -> RunPaths:
        for directory in (self.root, self.judgements_dir, self.clusters_dir, self.artifact_dir):
            directory.mkdir(parents=True, exist_ok=True)
        return self


def append_jsonl(path: Path, obj: Any) -> int:
    """Append one row, returning its byte offset for O(1) seeks later."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = stable_dumps(obj) + "\n"
    with open(path, "a", encoding="utf-8") as handle:
        handle.flush()
        offset = handle.tell()
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
    return offset


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def read_row_at(path: Path, offset: int) -> dict[str, Any]:
    """Read the single row stored at `offset` without scanning the file."""
    with open(path, encoding="utf-8") as handle:
        handle.seek(offset)
        return json.loads(handle.readline())


def row_id(judge_name: str, offset: int) -> str:
    return f"{judge_name}.jsonl:{offset}"


def split_row_id(value: str) -> tuple[str, int]:
    filename, _, offset = value.rpartition(":")
    return filename, int(offset)


def load_completed(path: Path) -> set[tuple[str, str, str]]:
    """Triples ``(sample_key, prompt_sha256, model_id)`` already answered.

    Keyed on the **cell**, not the judge name: two models behind one prompt are
    two independent measurements, and skipping the second because the first
    succeeded would silently halve the run.
    """
    done: set[tuple[str, str, str]] = set()
    for row in read_jsonl(path):
        if row.get("parse_ok") is True:
            done.add((row["sample_key"], row["prompt_sha256"], row["model_id"]))
    return done


def cells_in_file(path: Path) -> list[JudgeCell]:
    seen: dict[tuple[str, str, str], JudgeCell] = {}
    for row in read_jsonl(path):
        cell = JudgeCell(
            judge_name=row["judge_name"],
            prompt_sha256=row["prompt_sha256"],
            model_id=row["model_id"],
        )
        seen.setdefault(cell.as_tuple(), cell)
    return [seen[k] for k in sorted(seen)]


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def transcripts_sha256(rows: list[dict[str, Any]]) -> str:
    """Content hash of the stored transcripts, independent of file layout."""
    return sha256_text("\n".join(stable_dumps(row) for row in rows))


def judgements_sha256(paths: list[Path]) -> str:
    """Combined hash of every judgement file, used to invalidate derived files."""
    parts = []
    for path in sorted(paths):
        parts.append(f"{path.name}:{sha256_text(path.read_text(encoding='utf-8'))}")
    return sha256_text("|".join(parts))
