#!/usr/bin/env python3
"""Independently verify that every grounded label's offsets slice to its recorded excerpt.

Deliberately stdlib-only, and deliberately does NOT import ``transcript_judge``.
A verifier that reuses the grounding code it is checking inherits that code's
bugs and will agree with itself; re-slicing the stored text with plain string
indexing is the only way this catches an off-by-one in the ladder.

Checks, per resolved label:

* ``messages[message_index].text[char_start:char_end] == source_excerpt``, exactly.
* Reports (does not fail on) the count where ``judge_quote != source_excerpt`` --
  that divergence is expected at every tier above ``exact`` and is the record of
  what the ladder had to fold. It is a statistic, not an error.

Exit 0 if every resolved label slices correctly, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "run_dir", type=Path, help="run directory containing transcripts.jsonl and labels.jsonl"
    )
    args = ap.parse_args()

    transcripts_path = args.run_dir / "transcripts.jsonl"
    labels_path = args.run_dir / "labels.jsonl"
    for p in (transcripts_path, labels_path):
        if not p.exists():
            print(f"MISSING: {p}", file=sys.stderr)
            return 1

    # sample_key -> message_index -> text
    texts: dict[str, dict[int, str]] = {}
    for sample in read_jsonl(transcripts_path):
        texts[sample["sample_key"]] = {m["index"]: m["text"] for m in sample["messages"]}

    labels = read_jsonl(labels_path)
    resolved = [row for row in labels if row.get("resolved")]
    unresolved = [row for row in labels if not row.get("resolved")]

    mismatches: list[str] = []
    quote_differs = 0
    nfc_only = 0

    for row in resolved:
        key, idx = row["sample_key"], row["message_index"]
        start, end = row["char_start"], row["char_end"]
        expected = row["source_excerpt"]

        if key not in texts:
            mismatches.append(f"{row['label_id']}: sample_key {key!r} not in transcripts.jsonl")
            continue
        if idx not in texts[key]:
            mismatches.append(f"{row['label_id']}: message_index {idx} not in sample {key!r}")
            continue

        actual = texts[key][idx][start:end]
        if actual != expected:
            mismatches.append(
                f"{row['label_id']} ({key} msg {idx} [{start}:{end}])\n"
                f"    sliced  : {actual!r}\n"
                f"    recorded: {expected!r}"
            )
            continue

        judge_quote = row.get("judge_quote")
        if judge_quote is not None and judge_quote != expected:
            quote_differs += 1
            if unicodedata.normalize("NFC", judge_quote) == unicodedata.normalize("NFC", expected):
                nfc_only += 1

    print(f"labels total            : {len(labels)}")
    print(f"  resolved              : {len(resolved)}")
    print(f"  unresolved            : {len(unresolved)}")
    print(f"offset slice mismatches : {len(mismatches)}")
    print(f"judge_quote != excerpt  : {quote_differs} of {len(resolved)} resolved")
    print(f"  ...NFC-equivalent only: {nfc_only}")

    for m in mismatches:
        print(f"\nMISMATCH {m}")

    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
