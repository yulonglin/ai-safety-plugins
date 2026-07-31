#!/usr/bin/env python3
"""Measure candidate deterministic tripwire fire-rates against the real transcript corpus.

Same corpus and same extraction the LLM methodology hook saw (PostToolUse on
Bash/Write/Edit), so the fire counts are directly comparable to its 2,490 fires
/ ~85% no-finding rate. A tripwire that fires at that scale is not a tripwire.
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
OUT = Path("/tmp/claude/ef9473cf-tripwire-results.txt")

# --- the LLM hook's own pre-filters, replicated verbatim -------------------
_PYTHON_CMD = re.compile(r"(?:^|\s|&&|\|\||;)(?:uv\s+run\s+)?python3?\s", re.IGNORECASE)
_CODE_DATA_EXT = re.compile(r"\.(?:py|csv|json|jsonl)$", re.IGNORECASE)

# --- candidate tripwires ---------------------------------------------------
# Each is deliberately narrow: it must encode the *circularity*, not just the
# presence of a score/threshold/dict, or it degenerates into "fires on all
# research code".
TRIPWIRES = {
    # 1. A label/group/condition assigned by thresholding a score column.
    #    This is the circular-reasoning smell: outcome -> label -> measure outcome.
    "label_from_score": re.compile(
        r"\b(?:label|labels|group|groups|condition|category|is_[a-z_]+)\s*=\s*"
        r"[^=\n]*\b[a-z_]*(?:score|prob|logit|auc|acc|conf|pred)[a-z_]*\b\s*[<>]=?",
        re.IGNORECASE,
    ),
    # 2. A threshold/cutoff chosen using something named test (leakage).
    "threshold_on_test": re.compile(
        r"\b(?:threshold|thresh|cutoff|tau)[a-z_]*\s*=\s*[^\n]*\btest\b",
        re.IGNORECASE,
    ),
    # 2b. argmax-style threshold search over a test split.
    "best_thresh_on_test": re.compile(
        r"\bbest[a-z_]*(?:threshold|thresh|cutoff)[a-z_]*\b[^\n]*\btest\b",
        re.IGNORECASE,
    ),
    # 3. A hardcoded id -> experimental-condition mapping (should come from metadata).
    "hardcoded_id_condition": re.compile(
        r"[\{,]\s*([\"'])[\w.-]{6,}\1\s*:\s*([\"'])"
        r"(?:control|treatment|baseline|intervention|cond[a-z_]*|arm[a-z_]*)\2",
        re.IGNORECASE,
    ),
}

# Looser variants, to show what a *naive* version of each would have cost.
NAIVE = {
    "naive_any_score_assign": re.compile(r"\b[a-z_]*score[a-z_]*\s*=", re.IGNORECASE),
    "naive_any_threshold": re.compile(r"\b(?:threshold|thresh|cutoff)\b", re.IGNORECASE),
    "naive_any_test_word": re.compile(r"\btest\b", re.IGNORECASE),
}


def iter_tool_uses(path):
    """Yield (tool_name, payload_text) for each Bash/Write/Edit tool_use."""
    try:
        with open(path, "r", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or '"tool_use"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except (ValueError, TypeError):
                    continue
                msg = rec.get("message")
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    name = block.get("name")
                    inp = block.get("input")
                    if not isinstance(inp, dict):
                        continue
                    if name == "Bash":
                        cmd = inp.get("command")
                        if isinstance(cmd, str):
                            yield ("Bash", cmd, inp.get("command", ""))
                    elif name == "Write":
                        fp, c = inp.get("file_path", ""), inp.get("content")
                        if isinstance(c, str):
                            yield ("Write", c, fp)
                    elif name == "Edit":
                        fp, c = inp.get("file_path", ""), inp.get("new_string")
                        if isinstance(c, str):
                            yield ("Edit", c, fp)
    except OSError:
        return


def passes_prefilter(tool, payload, target):
    """Replicate the LLM hook's gate: only python commands / code+data files."""
    if tool == "Bash":
        return bool(_PYTHON_CMD.search(payload))
    return bool(_CODE_DATA_EXT.search(target or ""))


def main():
    if not PROJECTS.is_dir():
        print(f"FATAL: {PROJECTS} not found", file=sys.stderr)
        return 1

    transcripts = sorted(PROJECTS.glob("*/*.jsonl"))
    counts = Counter()
    naive_counts = Counter()
    samples = defaultdict(list)
    total_tool_uses = 0
    passed_prefilter = 0

    for t in transcripts:
        for tool, payload, target in iter_tool_uses(t):
            total_tool_uses += 1
            if not passes_prefilter(tool, payload, target):
                continue
            passed_prefilter += 1
            for name, rx in TRIPWIRES.items():
                m = rx.search(payload)
                if m:
                    counts[name] += 1
                    if len(samples[name]) < 6:
                        line = payload[max(0, m.start() - 60):m.end() + 60]
                        samples[name].append(
                            f"[{tool} {os.path.basename(target or '')}] "
                            + " ".join(line.split())
                        )
            for name, rx in NAIVE.items():
                if rx.search(payload):
                    naive_counts[name] += 1

    lines = []
    lines.append(f"transcripts scanned      : {len(transcripts)}")
    lines.append(f"Bash/Write/Edit uses     : {total_tool_uses}")
    lines.append(f"passed the hook prefilter: {passed_prefilter}   <-- the LLM hook's candidate pool")
    lines.append("")
    lines.append("=== CANDIDATE TRIPWIRES (narrow, circularity-encoding) ===")
    for name in TRIPWIRES:
        n = counts[name]
        pct = (100.0 * n / passed_prefilter) if passed_prefilter else 0.0
        lines.append(f"  {name:26s} {n:6d} fires  ({pct:.3f}% of pool)")
    lines.append("")
    lines.append("=== NAIVE VARIANTS (what a sloppy regex would have cost) ===")
    for name in NAIVE:
        n = naive_counts[name]
        pct = (100.0 * n / passed_prefilter) if passed_prefilter else 0.0
        lines.append(f"  {name:26s} {n:6d} fires  ({pct:.3f}% of pool)")
    lines.append("")
    lines.append("=== SAMPLE MATCHES (judge these by hand: real smell or false positive?) ===")
    for name in TRIPWIRES:
        lines.append(f"--- {name} ({counts[name]} total)")
        if not samples[name]:
            lines.append("    (no matches)")
        for s in samples[name]:
            lines.append(f"    {s[:220]}")
        lines.append("")

    text = "\n".join(lines)
    OUT.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
