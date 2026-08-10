#!/usr/bin/env python3
"""Stop hook: nudge when a research report ships without a working figure.

A findings document that argues from numbers and shows none is harder to check
than one that plots them, and the failure is quiet — a broken image renders as a
gap, and nobody notices until a reader asks. So the rule is deliberately about
the file on disk, not the markup: a report that *references* `fig.png` is only
credited with a figure if `fig.png` exists and has bytes in it. An absent or
zero-byte image is exactly the case a naive `path.exists()` check waves through.

Stdlib only, on purpose: a hook runs in whatever interpreter the harness has and
cannot assume a project virtualenv.

Detect-only. Emits `{"systemMessage": ...}` on stdout and exits 0 on every path,
including internal error — a nudge that blocks the Stop event would be worse
than the omission it is complaining about.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Documents whose whole job is to present findings. A note or a spec is not one.
REPORT_NAME = re.compile(
    r"report|analysis|findings|results|summary|writeup", re.IGNORECASE
)

MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\(\s*([^)\s]+)")
HTML_IMAGE = re.compile(r"<img\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)", re.IGNORECASE)
MERMAID_FENCE = re.compile(
    r"^[ \t]*(?:```|~~~)\s*mermaid\b", re.IGNORECASE | re.MULTILINE
)

REMOTE_PREFIXES = ("http://", "https://", "data:", "//")

NUDGE = """📊 **Report written without a working figure.**

{listing}

A findings document that argues from numbers reads better with at least one of:
- a plot (`from anthro_colors import use_anthropic_defaults` for house style)
- a ```mermaid fence for structure or flow
- an existing, non-empty image committed next to the report

Referenced-but-missing and zero-byte images are counted as *no figure* here, \
because that is how they render."""


def is_report(path: Path) -> bool:
    """A markdown file whose name or parent directory announces it as findings."""
    if path.suffix.lower() != ".md":
        return False
    return (
        bool(REPORT_NAME.search(path.stem))
        or REPORT_NAME.search(path.parent.name) is not None
    )


def referenced_images(text: str) -> list[str]:
    return [*MARKDOWN_IMAGE.findall(text), *HTML_IMAGE.findall(text)]


def has_working_figure(report: Path, text: str) -> bool:
    """True when the report carries a figure a reader would actually see."""
    if MERMAID_FENCE.search(text):
        return True

    for ref in referenced_images(text):
        if ref.startswith(REMOTE_PREFIXES):
            # A remote image is out of our reach to verify; take it at its word.
            return True
        target = Path(ref) if Path(ref).is_absolute() else report.parent / ref
        try:
            if target.is_file() and target.stat().st_size > 0:
                return True
        except OSError:
            continue
    return False


def edited_paths(transcript: Path, cwd: Path) -> list[Path]:
    """Files this session wrote or edited, oldest first, deduplicated."""
    seen: dict[str, Path] = {}
    try:
        lines = transcript.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") not in {"Write", "Edit", "NotebookEdit"}:
                continue
            raw = (block.get("input") or {}).get("file_path")
            if not isinstance(raw, str) or not raw:
                continue
            path = Path(raw)
            resolved = path if path.is_absolute() else cwd / path
            seen[str(resolved)] = resolved
    return list(seen.values())


def unillustrated(paths: list[Path]) -> list[Path]:
    out = []
    for path in paths:
        if not is_report(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not has_working_figure(path, text):
            out.append(path)
    return out


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if not isinstance(payload, dict):
        return 0

    # Set when the hook's own message re-triggered Stop; nudging again would loop.
    if payload.get("stop_hook_active"):
        return 0

    transcript = payload.get("transcript_path")
    if not isinstance(transcript, str) or not transcript:
        return 0
    cwd = Path(payload.get("cwd") or ".")

    bare = unillustrated(edited_paths(Path(transcript), cwd))
    if not bare:
        return 0

    listing = "\n".join(f"- `{path}`" for path in bare)
    json.dump({"systemMessage": NUDGE.format(listing=listing)}, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - a hook must never take the session down
        sys.exit(0)
