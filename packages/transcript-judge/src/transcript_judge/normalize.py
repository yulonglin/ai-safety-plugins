"""The single definition of "the text of a message".

Every offset in this package indexes the string this module returns, so the
rules here are deliberately unforgiving:

* no ``.strip()``, no whitespace collapsing, no unicode normalisation -- the
  stored text is the text, and any folding happens later in `ground` on a copy;
* multi-block assistant content joins with a literal ``"\\n\\n"`` in list order;
* a non-text block renders as a fixed placeholder and is counted, never dropped
  silently.

Bump `NORMALIZER_VERSION` whenever any of that changes: it is copied into every
manifest, so a run whose spans were computed under different rules is
identifiable after the fact.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

NORMALIZER_VERSION = 1

#: Joins the text of consecutive content blocks within one message.
BLOCK_JOIN = "\n\n"


def _block_type(block: Any) -> str:
    if isinstance(block, dict):
        return str(block.get("type", "unknown"))
    return str(getattr(block, "type", "unknown"))


def _block_text(block: Any) -> str | None:
    if _block_type(block) != "text":
        return None
    if isinstance(block, dict):
        return str(block.get("text", ""))
    return str(getattr(block, "text", ""))


def message_text(message: Any, stats: dict[str, int] | None = None) -> str:
    """Return the canonical text of one message.

    `stats`, when given, accumulates ``non_text_blocks_elided`` so the manifest
    can report how much of the transcript the judge never saw.
    """
    content = (
        message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
    )

    if content is None:
        return ""
    if isinstance(content, str):
        return content

    parts: list[str] = []
    for block in content:
        text = _block_text(block)
        if text is None:
            parts.append(f"[non-text block: {_block_type(block)}]")
            if stats is not None:
                stats["non_text_blocks_elided"] = stats.get("non_text_blocks_elided", 0) + 1
        else:
            parts.append(text)
    return BLOCK_JOIN.join(parts)


def message_phase(message: Any) -> str | None:
    """Inspect stashes a phase marker under ``internal``; most logs have none."""
    internal = (
        message.get("internal") if isinstance(message, dict) else getattr(message, "internal", None)
    )
    if isinstance(internal, dict):
        phase = internal.get("message_phase")
        return None if phase is None else str(phase)
    return None


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Any) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_dumps(obj: Any) -> str:
    """The only JSON serialiser used for anything that gets hashed or diffed.

    Byte-stability is load-bearing in three places -- ``transcripts_sha256``,
    ``input_data_sha256`` and the byte-identical cluster rerun -- so key order
    and separators are pinned here rather than left to each call site.
    """
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
